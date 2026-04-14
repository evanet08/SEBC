import json
import logging
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Count, Q

from .models import (
    Membre, TypeAyantDroit, AyantDroit, Cellule, Pays,
    NotificationGestionnaire, STATUT_CHOICES, ROLE_CHOICES
)
from .email_service import send_otp_email

logger = logging.getLogger(__name__)


# ============================================================
# PAGES PUBLIQUES
# ============================================================

def accueil(request):
    """Page d'accueil — double entrée : membres et candidats."""
    return render(request, 'sebc_app/accueil.html')


def page_login(request):
    """Page de connexion des membres."""
    # Si déjà connecté, redirect au dashboard
    membre_id = request.session.get('membre_id')
    if membre_id:
        return redirect('sebc_app:dashboard')
    return render(request, 'sebc_app/auth/login.html')


def page_candidature(request):
    """Formulaire de demande d'adhésion."""
    types_ayants_droits = TypeAyantDroit.objects.filter(est_actif=True).order_by('libelle')
    pays_list = Pays.objects.filter(est_actif=True).order_by('nom')
    return render(request, 'sebc_app/auth/candidature.html', {
        'types_ayants_droits': types_ayants_droits,
        'pays_list': pays_list,
    })


def dashboard(request):
    """Dashboard principal — nécessite une session membre."""
    membre_id = request.session.get('membre_id')
    if not membre_id:
        return redirect('sebc_app:login')

    try:
        membre = Membre.objects.get(id=membre_id, est_actif=True)
    except Membre.DoesNotExist:
        request.session.flush()
        return redirect('sebc_app:login')

    # Stats pour le dashboard
    stats = {
        'total_membres': Membre.objects.filter(est_actif=True).count(),
        'membres_approuves': Membre.objects.filter(statut='APPROUVE', est_actif=True).count(),
        'membres_en_attente': Membre.objects.filter(statut='EN_ATTENTE', est_actif=True).count(),
        'total_cellules': Cellule.objects.filter(est_active=True).count(),
    }

    # Stats par pays
    stats_par_pays = Membre.objects.filter(
        est_actif=True
    ).values(
        'pays_residence__nom'
    ).annotate(
        total=Count('id'),
        approuves=Count('id', filter=Q(statut='APPROUVE')),
        en_attente=Count('id', filter=Q(statut='EN_ATTENTE')),
    ).order_by('-total')

    # Stats par cellule
    stats_par_cellule = Cellule.objects.filter(
        est_active=True
    ).annotate(
        total_membres=Count('membres', filter=Q(membres__est_actif=True)),
        approuves=Count('membres', filter=Q(membres__statut='APPROUVE', membres__est_actif=True)),
        en_attente=Count('membres', filter=Q(membres__statut='EN_ATTENTE', membres__est_actif=True)),
    ).order_by('code')

    # Demandes récentes (pour gestionnaires)
    demandes_recentes = []
    if membre.is_gestionnaire():
        demandes_recentes = Membre.objects.filter(
            statut='EN_ATTENTE', est_actif=True
        ).order_by('-date_demande_adhesion')[:10]

    return render(request, 'sebc_app/dashboard.html', {
        'membre': membre,
        'stats': stats,
        'stats_par_pays': stats_par_pays,
        'stats_par_cellule': stats_par_cellule,
        'demandes_recentes': demandes_recentes,
    })


# ============================================================
# API AUTHENTIFICATION
# ============================================================

@csrf_exempt
@require_POST
def api_check_email(request):
    """Vérifie si un email existe dans la base des membres."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'exists': False, 'error': 'Requête invalide'})

    if not email:
        return JsonResponse({'exists': False, 'error': 'Email requis'})

    try:
        membre = Membre.objects.get(email=email, est_actif=True)
        has_password = bool(membre.mot_de_passe_hash)
        return JsonResponse({
            'exists': True,
            'validated': membre.email_verifie,
            'has_password': has_password,
            'statut': membre.statut,
            'user': {
                'nom': membre.nom,
                'prenom': membre.prenom,
                'telephone': membre.telephone_whatsapp,
                'role': membre.get_role_display(),
            }
        })
    except Membre.DoesNotExist:
        return JsonResponse({'exists': False})


@csrf_exempt
@require_POST
def api_login(request):
    """Connexion d'un membre (email + mot de passe)."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    try:
        membre = Membre.objects.get(email=email, est_actif=True)
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Email non reconnu.'})

    if not membre.email_verifie:
        return JsonResponse({
            'success': False,
            'email_not_verified': True,
            'error': 'Votre email n\'a pas encore été vérifié.'
        })

    if not membre.check_password(password):
        return JsonResponse({'success': False, 'error': 'Mot de passe incorrect.'})

    # Créer la session
    membre.derniere_connexion = timezone.now()
    membre.save(update_fields=['derniere_connexion'])
    request.session['membre_id'] = membre.id
    request.session['membre_nom'] = membre.nom_complet
    request.session['membre_role'] = membre.role

    needs_phone_verify = not membre.telephone_verifie

    return JsonResponse({
        'success': True,
        'redirect_url': '/dashboard/',
        'needs_contact_verification': needs_phone_verify,
        'email_verified': membre.email_verifie,
        'phone_verified': membre.telephone_verifie,
    })


@csrf_exempt
@require_POST
def api_request_otp(request):
    """Envoie un code OTP par email."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        method = data.get('method', 'EMAIL')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    try:
        membre = Membre.objects.get(email=email, est_actif=True)
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Email non trouvé.'})

    otp_code = membre.generate_otp(otp_type=method)

    if method == 'EMAIL':
        result = send_otp_email(email, otp_code, membre.prenom)
        if result['success']:
            return JsonResponse({'success': True, 'message': 'Code envoyé par email.'})
        else:
            return JsonResponse({'success': False, 'error': 'Erreur d\'envoi. Réessayez.'})
    else:
        # SMS/WhatsApp — à implémenter plus tard
        return JsonResponse({'success': False, 'error': 'Envoi SMS non encore disponible.'})


@csrf_exempt
@require_POST
def api_verify_otp(request):
    """Vérifie un code OTP."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        code = data.get('code', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    try:
        membre = Membre.objects.get(email=email, est_actif=True)
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Email non trouvé.'})

    if membre.verify_otp(code):
        # Marquer l'email comme vérifié
        membre.email_verifie = True
        membre.save(update_fields=['email_verifie'])
        return JsonResponse({'success': True, 'token': str(membre.uuid)})
    else:
        return JsonResponse({'success': False, 'error': 'Code incorrect ou expiré.'})


@csrf_exempt
@require_POST
def api_set_password(request):
    """Définit le mot de passe après vérification OTP."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        token = data.get('token', '')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    if len(password) < 6:
        return JsonResponse({'success': False, 'error': 'Le mot de passe doit avoir au moins 6 caractères.'})

    try:
        membre = Membre.objects.get(email=email, uuid=token, est_actif=True)
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session invalide.'})

    membre.set_password(password)
    membre.save(update_fields=['mot_de_passe_hash'])

    # Connecter automatiquement
    request.session['membre_id'] = membre.id
    request.session['membre_nom'] = membre.nom_complet
    request.session['membre_role'] = membre.role

    return JsonResponse({'success': True, 'redirect_url': '/dashboard/'})


@csrf_exempt
@require_POST
def api_logout(request):
    """Déconnexion."""
    request.session.flush()
    return JsonResponse({'success': True})


# ============================================================
# API CANDIDATURE (inscription nouveau membre)
# ============================================================

@csrf_exempt
@require_POST
def api_submit_candidature(request):
    """Soumission d'une candidature d'adhésion."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    # Champs obligatoires
    required_fields = ['nom', 'prenom', 'email', 'telephone_whatsapp']
    for field in required_fields:
        if not data.get(field, '').strip():
            return JsonResponse({'success': False, 'error': f'Le champ {field} est obligatoire.'})

    email = data['email'].strip().lower()

    # Vérifier unicité email
    if Membre.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Un compte existe déjà avec cet email.'})

    # Créer le membre EN_ATTENTE
    try:
        pays = None
        if data.get('pays_residence_id'):
            pays = Pays.objects.filter(id=data['pays_residence_id']).first()

        membre = Membre.objects.create(
            nom=data['nom'].strip().upper(),
            prenom=data['prenom'].strip().title(),
            email=email,
            telephone_whatsapp=data['telephone_whatsapp'].strip(),
            telephone_canada=data.get('telephone_canada', '').strip() or None,
            province_origine=data.get('province_origine', '').strip() or None,
            ville_residence=data.get('ville_residence', '').strip() or None,
            pays_residence=pays,
            nom_pere=data.get('nom_pere', '').strip() or None,
            nom_mere=data.get('nom_mere', '').strip() or None,
            nom_conjoint=data.get('nom_conjoint', '').strip() or None,
            noms_enfants=data.get('noms_enfants', '').strip() or None,
            noms_freres_soeurs=data.get('noms_freres_soeurs', '').strip() or None,
            nom_personne_referante=data.get('nom_personne_referante', '').strip() or None,
            tel_personne_referante=data.get('tel_personne_referante', '').strip() or None,
            email_personne_referante=data.get('email_personne_referante', '').strip() or None,
            statut='EN_ATTENTE',
        )

        # Créer les ayants droits
        ayants_droits = data.get('ayants_droits', [])
        for ad in ayants_droits:
            if ad.get('nom') and ad.get('type_lien_id'):
                try:
                    type_lien = TypeAyantDroit.objects.get(id=ad['type_lien_id'])
                    AyantDroit.objects.create(
                        membre=membre,
                        type_lien=type_lien,
                        nom=ad['nom'].strip().upper(),
                        prenom=ad.get('prenom', '').strip().title(),
                    )
                except TypeAyantDroit.DoesNotExist:
                    pass

        # Envoyer OTP pour vérification email
        otp_code = membre.generate_otp(otp_type='EMAIL')
        send_otp_email(email, otp_code, membre.prenom)

        # Notifier les gestionnaires configurés
        gestionnaires = NotificationGestionnaire.objects.filter(
            recevoir_demandes_adhesion=True, est_actif=True
        ).select_related('membre')
        # TODO: envoyer notifications aux gestionnaires

        return JsonResponse({
            'success': True,
            'message': 'Candidature soumise ! Vérifiez votre email pour le code de validation.',
            'membre_id': membre.id,
        })

    except Exception as e:
        logger.error(f"Erreur création candidature: {e}")
        return JsonResponse({'success': False, 'error': 'Erreur lors de la soumission. Réessayez.'})
