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
    NotificationGestionnaire, STATUT_CHOICES, ROLE_CHOICES,
    ParametreAssociation, Province, TypeSoutien,
    DocumentMembre, TYPE_DOCUMENT_CHOICES,
    Module, AccesModule,
    TypeMembre, Communication, CommunicationGroupe, CommunicationGroupeMembre,
    Meeting, MeetingInvite
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
    # Si déjà connecté, redirect selon le rôle
    membre_id = request.session.get('membre_id')
    if membre_id:
        try:
            m = Membre.objects.get(id=membre_id, est_actif=True)
            return redirect('sebc_app:dashboard' if m.is_gestionnaire() else 'sebc_app:membres')
        except Membre.DoesNotExist:
            request.session.flush()
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

    # Redirection intelligente selon le rôle
    redirect_url = '/dashboard/' if membre.is_gestionnaire() else '/membres/'

    return JsonResponse({
        'success': True,
        'redirect_url': redirect_url,
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

    redirect_url = '/dashboard/' if membre.is_gestionnaire() else '/membres/'
    return JsonResponse({'success': True, 'redirect_url': redirect_url})


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

        # Résoudre le parrain
        parrain = None
        if data.get('parrain_id'):
            parrain = Membre.objects.filter(id=data['parrain_id'], statut='APPROUVE', est_actif=True).first()

        membre = Membre.objects.create(
            nom=data['nom'].strip().upper(),
            prenom=data['prenom'].strip().title(),
            email=email,
            telephone_whatsapp=data['telephone_whatsapp'].strip(),
            telephone_canada=data.get('telephone_canada', '').strip() or None,
            province_origine=data.get('province_origine', '').strip() or None,
            ville_residence=data.get('ville_residence', '').strip() or None,
            pays_residence=pays,
            personne_referante=parrain,
            nom_personne_referante=parrain.nom_complet if parrain else None,
            tel_personne_referante=parrain.telephone_whatsapp if parrain else None,
            email_personne_referante=parrain.email if parrain else None,
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

        # Notifier le parrain
        if parrain:
            parrain_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:20px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
    <tr><td style="background:linear-gradient(135deg,#1a3a5c,#2c5f8a);padding:24px 30px;text-align:center">
        <h1 style="color:#fff;margin:0;font-size:22px">S.E.B.C — Dushigikirane</h1>
    </td></tr>
    <tr><td style="padding:30px">
        <p style="color:#333;font-size:15px;margin:0 0 16px">Bonjour {parrain.prenom},</p>
        <p style="color:#333;font-size:15px;line-height:1.6;margin:0 0 16px"><strong>{membre.prenom} {membre.nom}</strong> vient de soumettre une demande d'adhésion à l'association <strong>SEBC Dushigikirane</strong> en vous désignant comme parrain.</p>
        <div style="background:#f0f7ff;border-left:4px solid #1a3a5c;padding:14px 18px;border-radius:0 8px 8px 0;margin:16px 0">
            <p style="margin:0;font-size:14px;color:#1a3a5c"><strong>Candidat :</strong> {membre.prenom} {membre.nom}</p>
            <p style="margin:4px 0 0;font-size:14px;color:#1a3a5c"><strong>Email :</strong> {membre.email}</p>
            <p style="margin:4px 0 0;font-size:14px;color:#1a3a5c"><strong>Téléphone :</strong> {membre.telephone_whatsapp}</p>
        </div>
        <p style="color:#333;font-size:15px;line-height:1.6;margin:16px 0">Connectez-vous à votre espace membre pour <strong>valider ou non</strong> ce parrainage :</p>
        <div style="text-align:center;margin:20px 0">
            <a href="https://sebc-dushigikirane.pro/login/" style="display:inline-block;background:linear-gradient(135deg,#1a3a5c,#2c5f8a);color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px">Accéder à mon espace</a>
        </div>
        <hr style="border:none;border-top:1px solid #e8e8e8;margin:20px 0">
        <p style="color:#999;font-size:11px;margin:0">Si vous ne connaissez pas cette personne, ignorez cet email.</p>
    </td></tr>
    <tr><td style="background:#f8f9fa;padding:12px 30px;text-align:center">
        <p style="color:#aaa;font-size:11px;margin:0">&copy; S.E.B.C Dushigikirane</p>
    </td></tr>
</table>
</td></tr></table></body></html>"""
            from .email_service import send_brevo_email
            send_brevo_email(
                to_emails=[parrain.email],
                subject=f'[SEBC] Nouveau filleul : {membre.prenom} {membre.nom} demande votre parrainage',
                html_content=parrain_html,
            )

        return JsonResponse({
            'success': True,
            'message': 'Candidature soumise ! Vérifiez votre email pour le code de validation.',
            'membre_id': membre.id,
        })

    except Exception as e:
        logger.error(f"Erreur création candidature: {e}")
        return JsonResponse({'success': False, 'error': 'Erreur lors de la soumission. Réessayez.'})


# ============================================================
# HELPER — Vérifier accès admin
# ============================================================
def _get_admin_membre(request):
    """Retourne le membre connecté s'il est gestionnaire, sinon None."""
    membre_id = request.session.get('membre_id')
    if not membre_id:
        return None
    try:
        membre = Membre.objects.get(id=membre_id, est_actif=True)
        if membre.is_gestionnaire():
            return membre
    except Membre.DoesNotExist:
        pass
    return None


# ============================================================
# PAGE ADMINISTRATION
# ============================================================
def administration(request):
    """Page d'administration — CRUD de toutes les configurations."""
    membre = _get_admin_membre(request)
    if not membre:
        return redirect('sebc_app:login')

    pays_list = Pays.objects.all().order_by('nom')
    cellules = Cellule.objects.select_related('pays').all().order_by('code')
    provinces = Province.objects.select_related('pays').all().order_by('pays__nom', 'nom')
    types_ad = TypeAyantDroit.objects.all().order_by('libelle')
    types_soutien = TypeSoutien.objects.all().order_by('libelle')
    parametres = ParametreAssociation.objects.all().order_by('categorie', 'libelle')
    roles = ROLE_CHOICES
    modules_list = Module.objects.prefetch_related('acces').all().order_by('ordre')

    return render(request, 'sebc_app/administration.html', {
        'membre': membre,
        'active_page': 'administration',
        'pays_list': pays_list,
        'cellules': cellules,
        'provinces': provinces,
        'types_ad': types_ad,
        'types_soutien': types_soutien,
        'parametres': parametres,
        'roles': roles,
        'modules_list': modules_list,
    })


# ============================================================
# API CRUD ADMINISTRATION
# ============================================================

@csrf_exempt
@require_POST
def api_admin_pays(request):
    """CRUD pays : action = list|create|update|delete|toggle."""
    if not _get_admin_membre(request):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)

    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    if action == 'list':
        items = list(Pays.objects.all().values('id', 'nom', 'code_iso', 'indicatif_tel', 'est_actif').order_by('nom'))
        return JsonResponse({'success': True, 'items': items})

    elif action == 'create':
        nom = data.get('nom', '').strip()
        if not nom:
            return JsonResponse({'success': False, 'error': 'Le nom est obligatoire.'})
        if Pays.objects.filter(nom=nom).exists():
            return JsonResponse({'success': False, 'error': 'Ce pays existe déjà.'})
        obj = Pays.objects.create(
            nom=nom,
            code_iso=data.get('code_iso', '').strip().upper() or None,
            indicatif_tel=data.get('indicatif_tel', '').strip() or None,
        )
        return JsonResponse({'success': True, 'id': obj.id, 'message': f'Pays "{nom}" créé.'})

    elif action == 'update':
        try:
            obj = Pays.objects.get(id=data.get('id'))
            if data.get('nom'):
                obj.nom = data['nom'].strip()
            if 'code_iso' in data:
                obj.code_iso = data['code_iso'].strip().upper() or None
            if 'indicatif_tel' in data:
                obj.indicatif_tel = data['indicatif_tel'].strip() or None
            obj.save()
            return JsonResponse({'success': True, 'message': 'Mis à jour.'})
        except Pays.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Pays introuvable.'})

    elif action == 'toggle':
        try:
            obj = Pays.objects.get(id=data.get('id'))
            obj.est_actif = not obj.est_actif
            obj.save(update_fields=['est_actif'])
            return JsonResponse({'success': True, 'est_actif': obj.est_actif})
        except Pays.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'delete':
        try:
            obj = Pays.objects.get(id=data.get('id'))
            if obj.membres.exists() or obj.provinces.exists():
                return JsonResponse({'success': False, 'error': 'Impossible : des membres ou provinces sont liés.'})
            obj.delete()
            return JsonResponse({'success': True, 'message': 'Supprimé.'})
        except Pays.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


@csrf_exempt
@require_POST
def api_admin_cellules(request):
    """CRUD cellules."""
    if not _get_admin_membre(request):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    if action == 'list':
        items = list(Cellule.objects.select_related('pays').values(
            'id', 'code', 'nom', 'pays__nom', 'pays__id', 'est_active'
        ).order_by('code'))
        return JsonResponse({'success': True, 'items': items})

    elif action == 'create':
        code = data.get('code', '').strip().upper()
        if not code:
            return JsonResponse({'success': False, 'error': 'Le code est obligatoire.'})
        if Cellule.objects.filter(code=code).exists():
            return JsonResponse({'success': False, 'error': 'Ce code de cellule existe déjà.'})
        pays = Pays.objects.filter(id=data.get('pays_id')).first() if data.get('pays_id') else None
        obj = Cellule.objects.create(code=code, nom=data.get('nom', '').strip() or None, pays=pays)
        return JsonResponse({'success': True, 'id': obj.id, 'message': f'Cellule "{code}" créée.'})

    elif action == 'update':
        try:
            obj = Cellule.objects.get(id=data.get('id'))
            if data.get('code'):
                obj.code = data['code'].strip().upper()
            if 'nom' in data:
                obj.nom = data['nom'].strip() or None
            if 'pays_id' in data:
                obj.pays = Pays.objects.filter(id=data['pays_id']).first() if data['pays_id'] else None
            obj.save()
            return JsonResponse({'success': True, 'message': 'Mis à jour.'})
        except Cellule.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'toggle':
        try:
            obj = Cellule.objects.get(id=data.get('id'))
            obj.est_active = not obj.est_active
            obj.save(update_fields=['est_active'])
            return JsonResponse({'success': True, 'est_active': obj.est_active})
        except Cellule.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'delete':
        try:
            obj = Cellule.objects.get(id=data.get('id'))
            if obj.membres.exists():
                return JsonResponse({'success': False, 'error': 'Impossible : des membres sont affectés.'})
            obj.delete()
            return JsonResponse({'success': True, 'message': 'Supprimée.'})
        except Cellule.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


@csrf_exempt
@require_POST
def api_admin_provinces(request):
    """CRUD provinces."""
    if not _get_admin_membre(request):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    if action == 'list':
        items = list(Province.objects.select_related('pays').values(
            'id', 'nom', 'pays__nom', 'pays__id', 'est_actif'
        ).order_by('pays__nom', 'nom'))
        return JsonResponse({'success': True, 'items': items})

    elif action == 'create':
        nom = data.get('nom', '').strip()
        pays_id = data.get('pays_id')
        if not nom or not pays_id:
            return JsonResponse({'success': False, 'error': 'Nom et pays obligatoires.'})
        try:
            pays = Pays.objects.get(id=pays_id)
        except Pays.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Pays introuvable.'})
        if Province.objects.filter(nom=nom, pays=pays).exists():
            return JsonResponse({'success': False, 'error': 'Cette province existe déjà pour ce pays.'})
        obj = Province.objects.create(nom=nom, pays=pays)
        return JsonResponse({'success': True, 'id': obj.id, 'message': f'Province "{nom}" créée.'})

    elif action == 'update':
        try:
            obj = Province.objects.get(id=data.get('id'))
            if data.get('nom'):
                obj.nom = data['nom'].strip()
            if 'pays_id' in data and data['pays_id']:
                obj.pays = Pays.objects.get(id=data['pays_id'])
            obj.save()
            return JsonResponse({'success': True, 'message': 'Mis à jour.'})
        except Province.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'toggle':
        try:
            obj = Province.objects.get(id=data.get('id'))
            obj.est_actif = not obj.est_actif
            obj.save(update_fields=['est_actif'])
            return JsonResponse({'success': True, 'est_actif': obj.est_actif})
        except Province.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'delete':
        try:
            obj = Province.objects.get(id=data.get('id'))
            obj.delete()
            return JsonResponse({'success': True, 'message': 'Supprimée.'})
        except Province.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


@csrf_exempt
@require_POST
def api_admin_types_ad(request):
    """CRUD types d'ayants droits."""
    if not _get_admin_membre(request):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    if action == 'list':
        items = list(TypeAyantDroit.objects.all().values('id', 'libelle', 'description', 'est_actif').order_by('libelle'))
        return JsonResponse({'success': True, 'items': items})

    elif action == 'create':
        libelle = data.get('libelle', '').strip()
        if not libelle:
            return JsonResponse({'success': False, 'error': 'Le libellé est obligatoire.'})
        if TypeAyantDroit.objects.filter(libelle=libelle).exists():
            return JsonResponse({'success': False, 'error': 'Ce type existe déjà.'})
        obj = TypeAyantDroit.objects.create(libelle=libelle, description=data.get('description', '').strip() or None)
        return JsonResponse({'success': True, 'id': obj.id, 'message': f'Type "{libelle}" créé.'})

    elif action == 'update':
        try:
            obj = TypeAyantDroit.objects.get(id=data.get('id'))
            if data.get('libelle'):
                obj.libelle = data['libelle'].strip()
            if 'description' in data:
                obj.description = data['description'].strip() or None
            obj.save()
            return JsonResponse({'success': True, 'message': 'Mis à jour.'})
        except TypeAyantDroit.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'toggle':
        try:
            obj = TypeAyantDroit.objects.get(id=data.get('id'))
            obj.est_actif = not obj.est_actif
            obj.save(update_fields=['est_actif'])
            return JsonResponse({'success': True, 'est_actif': obj.est_actif})
        except TypeAyantDroit.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'delete':
        try:
            obj = TypeAyantDroit.objects.get(id=data.get('id'))
            if obj.ayants_droits.exists():
                return JsonResponse({'success': False, 'error': 'Impossible : des ayants droits utilisent ce type.'})
            obj.delete()
            return JsonResponse({'success': True, 'message': 'Supprimé.'})
        except TypeAyantDroit.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


@csrf_exempt
@require_POST
def api_admin_types_soutien(request):
    """CRUD types de soutien."""
    if not _get_admin_membre(request):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    if action == 'list':
        items = list(TypeSoutien.objects.all().values(
            'id', 'libelle', 'montant', 'description', 'nombre_temoins_requis', 'est_actif'
        ).order_by('libelle'))
        # Convert Decimal to float for JSON
        for item in items:
            item['montant'] = float(item['montant'])
        return JsonResponse({'success': True, 'items': items})

    elif action == 'create':
        libelle = data.get('libelle', '').strip()
        if not libelle:
            return JsonResponse({'success': False, 'error': 'Le libellé est obligatoire.'})
        obj = TypeSoutien.objects.create(
            libelle=libelle,
            montant=data.get('montant', 0),
            description=data.get('description', '').strip() or None,
            nombre_temoins_requis=data.get('nombre_temoins_requis', 3),
        )
        return JsonResponse({'success': True, 'id': obj.id, 'message': f'Type "{libelle}" créé.'})

    elif action == 'update':
        try:
            obj = TypeSoutien.objects.get(id=data.get('id'))
            if data.get('libelle'):
                obj.libelle = data['libelle'].strip()
            if 'montant' in data:
                obj.montant = data['montant']
            if 'description' in data:
                obj.description = data['description'].strip() or None
            if 'nombre_temoins_requis' in data:
                obj.nombre_temoins_requis = data['nombre_temoins_requis']
            obj.save()
            return JsonResponse({'success': True, 'message': 'Mis à jour.'})
        except TypeSoutien.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'toggle':
        try:
            obj = TypeSoutien.objects.get(id=data.get('id'))
            obj.est_actif = not obj.est_actif
            obj.save(update_fields=['est_actif'])
            return JsonResponse({'success': True, 'est_actif': obj.est_actif})
        except TypeSoutien.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'delete':
        try:
            obj = TypeSoutien.objects.get(id=data.get('id'))
            obj.delete()
            return JsonResponse({'success': True, 'message': 'Supprimé.'})
        except TypeSoutien.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


@csrf_exempt
@require_POST
def api_admin_parametres(request):
    """CRUD paramètres association."""
    if not _get_admin_membre(request):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    if action == 'list':
        items = list(ParametreAssociation.objects.all().values(
            'id', 'cle', 'libelle', 'valeur', 'type_valeur', 'description', 'categorie', 'modifiable'
        ).order_by('categorie', 'libelle'))
        return JsonResponse({'success': True, 'items': items})

    elif action == 'create':
        cle = data.get('cle', '').strip()
        libelle = data.get('libelle', '').strip()
        if not cle or not libelle:
            return JsonResponse({'success': False, 'error': 'Clé et libellé obligatoires.'})
        if ParametreAssociation.objects.filter(cle=cle).exists():
            return JsonResponse({'success': False, 'error': 'Cette clé existe déjà.'})
        obj = ParametreAssociation.objects.create(
            cle=cle, libelle=libelle,
            valeur=data.get('valeur', ''),
            type_valeur=data.get('type_valeur', 'STRING'),
            description=data.get('description', '').strip() or None,
            categorie=data.get('categorie', 'general').strip(),
        )
        return JsonResponse({'success': True, 'id': obj.id, 'message': f'Paramètre "{libelle}" créé.'})

    elif action == 'update':
        try:
            obj = ParametreAssociation.objects.get(id=data.get('id'))
            if 'valeur' in data:
                obj.valeur = data['valeur']
            if data.get('libelle'):
                obj.libelle = data['libelle'].strip()
            if 'description' in data:
                obj.description = data['description'].strip() or None
            if data.get('categorie'):
                obj.categorie = data['categorie'].strip()
            if data.get('type_valeur'):
                obj.type_valeur = data['type_valeur']
            obj.save()
            return JsonResponse({'success': True, 'message': 'Mis à jour.'})
        except ParametreAssociation.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'delete':
        try:
            obj = ParametreAssociation.objects.get(id=data.get('id'))
            obj.delete()
            return JsonResponse({'success': True, 'message': 'Supprimé.'})
        except ParametreAssociation.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


@csrf_exempt
@require_POST
def api_admin_roles(request):
    """Gestion des rôles des membres."""
    if not _get_admin_membre(request):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    if action == 'list':
        members = list(Membre.objects.filter(est_actif=True).values(
            'id', 'nom', 'prenom', 'email', 'role', 'statut', 'est_superadmin'
        ).order_by('nom'))
        return JsonResponse({'success': True, 'items': members, 'roles': ROLE_CHOICES})

    elif action == 'update_role':
        try:
            membre = Membre.objects.get(id=data.get('membre_id'))
            new_role = data.get('role', '')
            if new_role not in dict(ROLE_CHOICES):
                return JsonResponse({'success': False, 'error': 'Rôle invalide.'})
            membre.role = new_role
            membre.save(update_fields=['role'])
            return JsonResponse({'success': True, 'message': f'Rôle de {membre.nom_complet} mis à jour.'})
        except Membre.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Membre introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


# ============================================================
# API ADMIN — MODULES
# ============================================================
@csrf_exempt
@require_POST
def api_admin_modules(request):
    """CRUD Modules."""
    if not _get_admin_membre(request):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    if action == 'update':
        try:
            mod = Module.objects.get(id=data.get('id'))
            if 'nom' in data: mod.nom = data['nom']
            if 'url' in data: mod.url = data['url']
            if 'icone' in data: mod.icone = data['icone']
            if 'couleur' in data: mod.couleur = data['couleur']
            if 'ordre' in data: mod.ordre = data['ordre']
            if 'visible_sidebar' in data: mod.visible_sidebar = data['visible_sidebar']
            if 'requiert_approbation' in data: mod.requiert_approbation = data['requiert_approbation']
            mod.save()
            return JsonResponse({'success': True, 'message': f'Module "{mod.nom}" mis à jour.'})
        except Module.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Module introuvable.'})

    elif action == 'toggle':
        try:
            mod = Module.objects.get(id=data.get('id'))
            mod.est_actif = not mod.est_actif
            mod.save(update_fields=['est_actif'])
            return JsonResponse({'success': True, 'message': f'Module {"activé" if mod.est_actif else "désactivé"}.'})
        except Module.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


# ============================================================
# HELPER — Vérifier accès membre connecté
# ============================================================
def _get_logged_membre(request):
    """Retourne le membre connecté ou None."""
    membre_id = request.session.get('membre_id')
    if not membre_id:
        return None
    try:
        return Membre.objects.get(id=membre_id, est_actif=True)
    except Membre.DoesNotExist:
        return None


# ============================================================
# PAGE MEMBRE (espace personnel)
# ============================================================
def page_membres(request):
    """Espace personnel du membre — profil, famille, ayants droits, documents, parrainage."""
    membre = _get_logged_membre(request)
    if not membre:
        return redirect('sebc_app:login')

    # Ayants droits
    ayants_droits = AyantDroit.objects.filter(
        membre=membre, est_actif=True
    ).select_related('type_lien').order_by('nom')

    # Documents
    documents = DocumentMembre.objects.filter(membre=membre).order_by('-date_upload')

    # Filleuls (membres que j'ai parrainé)
    filleuls = Membre.objects.filter(
        personne_referante=membre, est_actif=True
    ).order_by('-date_demande_adhesion')

    # Parrain du membre
    parrain = membre.personne_referante

    # Types pour les selects
    types_ad = TypeAyantDroit.objects.filter(est_actif=True).order_by('libelle')
    pays_list = Pays.objects.filter(est_actif=True).order_by('nom')
    provinces = Province.objects.filter(est_actif=True).select_related('pays').order_by('pays__nom', 'nom')

    # Statistiques
    from django.db.models import Count
    stats = {
        'total_membres': Membre.objects.filter(est_actif=True, statut='APPROUVE').count(),
        'total_cellules': Cellule.objects.filter(est_active=True).count(),
        'total_pays': Pays.objects.filter(est_actif=True, membres__isnull=False).distinct().count(),
        'mes_ayants_droits': ayants_droits.count(),
        'mes_filleuls': filleuls.count(),
    }

    return render(request, 'sebc_app/membres.html', {
        'membre': membre,
        'active_page': 'membres',
        'ayants_droits': ayants_droits,
        'documents': documents,
        'filleuls': filleuls,
        'parrain': parrain,
        'types_ad': types_ad,
        'pays_list': pays_list,
        'provinces': provinces,
        'types_documents': TYPE_DOCUMENT_CHOICES,
        'stats': stats,
    })


# ============================================================
# API — Vérifier parrain (étape 1 candidature)
# ============================================================
@csrf_exempt
@require_POST
def api_check_parrain(request):
    """Vérifie si un parrain existe via email ou téléphone."""
    try:
        data = json.loads(request.body)
        contact = data.get('contact', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    if not contact:
        return JsonResponse({'success': False, 'error': 'Veuillez saisir un email ou téléphone.'})

    # Chercher par email ou téléphone
    parrain = Membre.objects.filter(
        Q(email__iexact=contact) | Q(telephone_whatsapp=contact),
        est_actif=True, statut='APPROUVE'
    ).first()

    if not parrain:
        return JsonResponse({
            'success': False,
            'error': 'Aucun membre approuvé trouvé avec cette information. Vérifiez l\'email ou le numéro de votre parrain.'
        })

    return JsonResponse({
        'success': True,
        'parrain_id': parrain.id,
        'parrain_email': parrain.email,
        'parrain_display': f"{parrain.prenom} {parrain.nom[0]}.",  # Initiale du nom seulement
    })


# ============================================================
# API — Mise à jour profil membre (self-service)
# ============================================================
@csrf_exempt
@require_POST
def api_membre_update_profile(request):
    """Met à jour les informations du profil du membre connecté."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    try:
        data = json.loads(request.body)
        section = data.get('section', 'identification')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    if section == 'identification':
        fields_map = {
            'telephone_canada': 'telephone_canada',
            'ville_residence': 'ville_residence',
            'adresse': 'adresse',
        }
        for key, field in fields_map.items():
            if key in data:
                setattr(membre, field, data[key].strip() or None)
        if 'pays_residence_id' in data and data['pays_residence_id']:
            membre.pays_residence = Pays.objects.filter(id=data['pays_residence_id']).first()
        if 'province_origine' in data:
            membre.province_origine = data['province_origine'].strip() or None
        membre.save()
        return JsonResponse({'success': True, 'message': 'Identification mise à jour.'})

    elif section == 'famille':
        famille_fields = ['nom_pere', 'nom_mere', 'nom_conjoint', 'noms_enfants', 'noms_freres_soeurs']
        for f in famille_fields:
            if f in data:
                setattr(membre, f, data[f].strip() or None)
        membre.save()
        return JsonResponse({'success': True, 'message': 'Informations familiales mises à jour.'})

    return JsonResponse({'success': False, 'error': 'Section inconnue.'})


# ============================================================
# API — CRUD Ayants droits (self-service membre)
# ============================================================
@csrf_exempt
@require_POST
def api_membre_ayants_droits(request):
    """CRUD ayants droits du membre connecté."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    try:
        data = json.loads(request.body)
        action = data.get('action', 'list')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    if action == 'list':
        items = list(AyantDroit.objects.filter(
            membre=membre, est_actif=True
        ).select_related('type_lien').values(
            'id', 'nom', 'prenom', 'type_lien__libelle', 'type_lien__id',
            'date_naissance', 'est_approuve'
        ).order_by('nom'))
        return JsonResponse({'success': True, 'items': items})

    elif action == 'create':
        type_lien_id = data.get('type_lien_id')
        nom = data.get('nom', '').strip().upper()
        prenom = data.get('prenom', '').strip().title()
        if not type_lien_id or not nom:
            return JsonResponse({'success': False, 'error': 'Type de lien et nom obligatoires.'})
        try:
            type_lien = TypeAyantDroit.objects.get(id=type_lien_id, est_actif=True)
        except TypeAyantDroit.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Type invalide.'})
        ad = AyantDroit.objects.create(
            membre=membre, type_lien=type_lien, nom=nom, prenom=prenom,
            date_naissance=data.get('date_naissance') or None,
        )
        return JsonResponse({'success': True, 'id': ad.id, 'message': f'Ayant droit "{nom}" ajouté.'})

    elif action == 'update':
        try:
            ad = AyantDroit.objects.get(id=data.get('id'), membre=membre)
            if data.get('nom'):
                ad.nom = data['nom'].strip().upper()
            if data.get('prenom'):
                ad.prenom = data['prenom'].strip().title()
            if 'type_lien_id' in data:
                ad.type_lien = TypeAyantDroit.objects.get(id=data['type_lien_id'])
            if 'date_naissance' in data:
                ad.date_naissance = data['date_naissance'] or None
            ad.save()
            return JsonResponse({'success': True, 'message': 'Mis à jour.'})
        except AyantDroit.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    elif action == 'delete':
        try:
            ad = AyantDroit.objects.get(id=data.get('id'), membre=membre)
            ad.est_actif = False
            ad.save(update_fields=['est_actif'])
            return JsonResponse({'success': True, 'message': 'Supprimé.'})
        except AyantDroit.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Introuvable.'})

    return JsonResponse({'success': False, 'error': 'Action inconnue.'})


# ============================================================
# API — Documents membre (upload / list)
# ============================================================
@csrf_exempt
def api_membre_documents(request):
    """Upload et liste des documents du membre."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    if request.method == 'POST':
        # Upload
        fichier = request.FILES.get('fichier')
        type_doc = request.POST.get('type_document', 'AUTRE')
        if not fichier:
            return JsonResponse({'success': False, 'error': 'Aucun fichier fourni.'})
        doc = DocumentMembre.objects.create(
            membre=membre,
            type_document=type_doc,
            fichier=fichier,
            nom_fichier=fichier.name,
            description=request.POST.get('description', '').strip() or None,
        )
        return JsonResponse({'success': True, 'id': doc.id, 'message': 'Document téléchargé.'})

    elif request.method == 'GET':
        items = list(DocumentMembre.objects.filter(membre=membre).values(
            'id', 'type_document', 'nom_fichier', 'est_valide', 'date_upload'
        ).order_by('-date_upload'))
        for item in items:
            item['date_upload'] = item['date_upload'].strftime('%d/%m/%Y %H:%M') if item['date_upload'] else ''
            item['type_display'] = dict(TYPE_DOCUMENT_CHOICES).get(item['type_document'], item['type_document'])
        return JsonResponse({'success': True, 'items': items})

    return JsonResponse({'success': False, 'error': 'Méthode non supportée.'})


# ============================================================
# API — Parrain valide un filleul
# ============================================================
@csrf_exempt
@require_POST
def api_valider_filleul(request):
    """Le parrain valide un de ses filleuls."""
    parrain = _get_logged_membre(request)
    if not parrain:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    try:
        data = json.loads(request.body)
        filleul_id = data.get('filleul_id')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    try:
        filleul = Membre.objects.get(
            id=filleul_id, personne_referante=parrain, est_actif=True
        )
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Filleul introuvable.'})

    filleul.parrain_valide = True
    filleul.date_validation_parrain = timezone.now()
    filleul.save(update_fields=['parrain_valide', 'date_validation_parrain'])

    return JsonResponse({
        'success': True,
        'message': f'{filleul.nom_complet} a été validé.'
    })


# ============================================================
# API — Relancer le parrain (rappel validation)
# ============================================================
@csrf_exempt
@require_POST
def api_relancer_parrain(request):
    """Le membre envoie un rappel à son parrain pour validation."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    if membre.parrain_valide:
        return JsonResponse({'success': False, 'error': 'Votre parrain vous a déjà validé.'})

    parrain = membre.personne_referante
    if not parrain:
        return JsonResponse({'success': False, 'error': 'Aucun parrain enregistré.'})

    relance_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:20px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
    <tr><td style="background:linear-gradient(135deg,#d97706,#f59e0b);padding:24px 30px;text-align:center">
        <h1 style="color:#fff;margin:0;font-size:22px">⏰ Rappel — S.E.B.C Dushigikirane</h1>
    </td></tr>
    <tr><td style="padding:30px">
        <p style="color:#333;font-size:15px;margin:0 0 16px">Bonjour {parrain.prenom},</p>
        <p style="color:#333;font-size:15px;line-height:1.6;margin:0 0 16px"><strong>{membre.prenom} {membre.nom}</strong> attend toujours votre validation de parrainage pour finaliser son adhésion à l'association SEBC Dushigikirane.</p>
        <div style="background:#fffbeb;border-left:4px solid #d97706;padding:14px 18px;border-radius:0 8px 8px 0;margin:16px 0">
            <p style="margin:0;font-size:14px;color:#92400e">Votre filleul(e) ne pourra pas avancer dans le processus d'adhésion tant que vous n'aurez pas confirmé le parrainage.</p>
        </div>
        <div style="text-align:center;margin:24px 0">
            <a href="https://sebc-dushigikirane.pro/login/" style="display:inline-block;background:linear-gradient(135deg,#1a3a5c,#2c5f8a);color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px">Valider maintenant</a>
        </div>
    </td></tr>
    <tr><td style="background:#f8f9fa;padding:12px 30px;text-align:center">
        <p style="color:#aaa;font-size:11px;margin:0">&copy; S.E.B.C Dushigikirane</p>
    </td></tr>
</table>
</td></tr></table></body></html>"""

    from .email_service import send_brevo_email
    result = send_brevo_email(
        to_emails=[parrain.email],
        subject=f'[SEBC] Rappel : {membre.prenom} {membre.nom} attend votre validation',
        html_content=relance_html,
    )

    if result.get('success'):
        return JsonResponse({'success': True, 'message': f'Rappel envoyé à {parrain.prenom}.'})
    return JsonResponse({'success': False, 'error': "Erreur d'envoi. Réessayez."})


# ============================================================
# PAGE COMMUNICATION
# ============================================================
def page_communication(request):
    """Page Communication — messagerie interne."""
    membre = _get_logged_membre(request)
    if not membre:
        return redirect('sebc_app:login')
    return render(request, 'sebc_app/communication.html', {
        'membre': membre,
        'active_page': 'communication',
    })


# ============================================================
# API COMMUNICATION — CONTACTS
# ============================================================
@csrf_exempt
def api_communication_contacts(request):
    """Retourne la liste des contacts pour la messagerie."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    # Tous les membres actifs/approuvés
    members = Membre.objects.filter(
        est_actif=True, statut='APPROUVE'
    ).select_related('cellule', 'type_membre').order_by('nom', 'prenom')

    members_data = [{
        'id': m.id,
        'nom_complet': m.nom_complet,
        'email': m.email,
        'type_membre': m.type_membre.libelle if m.type_membre else 'Membre',
        'cellule': m.cellule.code if m.cellule else None,
    } for m in members]

    # Cellules avec comptage
    cellules = Cellule.objects.filter(est_active=True).annotate(
        count=Count('membres', filter=Q(membres__est_actif=True, membres__statut='APPROUVE'))
    ).order_by('code')
    cellules_data = [{'id': c.id, 'code': c.code, 'nom': c.nom or c.code, 'count': c.count} for c in cellules]

    # Types de membres avec comptage
    types = TypeMembre.objects.filter(est_actif=True).annotate(
        count=Count('membres', filter=Q(membres__est_actif=True, membres__statut='APPROUVE'))
    ).order_by('libelle')
    types_data = [{'id': t.id, 'libelle': str(t), 'count': t.count} for t in types]

    # Groupes personnalisés (ceux dont le membre fait partie)
    group_ids = CommunicationGroupeMembre.objects.filter(
        membre=membre
    ).values_list('groupe_id', flat=True)
    groups = CommunicationGroupe.objects.filter(
        Q(id__in=group_ids) | Q(createur=membre), est_actif=True
    ).distinct().annotate(
        count=Count('membres_groupe')
    )
    groups_data = [{
        'id': g.id, 'nom': g.nom, 'description': g.description,
        'couleur': g.couleur_avatar, 'count': g.count,
        'is_owner': g.createur_id == membre.id,
        'members': list(g.membres_groupe.values_list('membre__nom', flat=True)),
    } for g in groups]

    return JsonResponse({
        'success': True,
        'members': members_data,
        'cellules': cellules_data,
        'types_membres': types_data,
        'custom_groups': groups_data,
    })


# ============================================================
# API COMMUNICATION — THREADS
# ============================================================
@csrf_exempt
def api_communication_threads(request):
    """Retourne les threads avec les derniers messages pour ce membre."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    from django.db.models import Max, Subquery, OuterRef

    # Trouver tous les threads où ce membre est impliqué
    threads_sent = Communication.objects.filter(sender=membre).values_list('thread_id', flat=True).distinct()
    threads_recv = Communication.objects.filter(target_membre=membre).values_list('thread_id', flat=True).distinct()
    # Threads de groupes/cellules/national
    all_thread_ids = set(threads_sent) | set(threads_recv)
    # Aussi les threads national/general
    all_thread_ids.add('national')
    all_thread_ids.add('general')
    # Cellule du membre
    if membre.cellule_id:
        all_thread_ids.add(f'cell_{membre.cellule_id}')

    threads = []
    for tid in all_thread_ids:
        if not tid:
            continue
        last_msg = Communication.objects.filter(thread_id=tid).order_by('-created_at').first()
        if not last_msg:
            continue
        unread = Communication.objects.filter(
            thread_id=tid, is_read=False
        ).exclude(sender=membre).count()
        threads.append({
            'thread_id': tid,
            'last_message': last_msg.message[:60] if last_msg.message else '',
            'last_time': last_msg.created_at.strftime('%H:%M') if last_msg.created_at else '',
            'unread': unread,
        })

    return JsonResponse({'success': True, 'threads': threads})


# ============================================================
# API COMMUNICATION — GET MESSAGES
# ============================================================
@csrf_exempt
def api_communication_messages(request):
    """Retourne les messages d'un thread."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    thread_id = request.GET.get('thread_id', '')
    if not thread_id:
        return JsonResponse({'success': True, 'messages': []})

    msgs = Communication.objects.filter(thread_id=thread_id).order_by('created_at')[:100]

    # Marquer comme lus
    msgs.filter(is_read=False).exclude(sender=membre).update(is_read=True, read_at=timezone.now())

    messages_data = []
    for m in msgs:
        att = None
        if m.attachment:
            att = {'url': m.attachment.url, 'name': m.attachment_name, 'type': m.attachment_type}
        messages_data.append({
            'id': m.id,
            'sender_id': m.sender_id,
            'sender_name': m.sender_name,
            'message': m.message,
            'subject': m.subject,
            'attachment': att,
            'created_at': m.created_at.strftime('%Y-%m-%d %H:%M') if m.created_at else '',
            'time': m.created_at.strftime('%H:%M') if m.created_at else '',
        })

    return JsonResponse({'success': True, 'messages': messages_data})


# ============================================================
# API COMMUNICATION — SEND MESSAGE
# ============================================================
@csrf_exempt
@require_POST
def api_communication_send(request):
    """Envoie un message dans un thread."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    thread_id = data.get('thread_id', '')
    message = data.get('message', '').strip()
    if not message:
        return JsonResponse({'success': False, 'error': 'Message vide'})

    scope = data.get('scope', 'individual')
    subject = data.get('subject', '')

    comm = Communication.objects.create(
        sender=membre,
        sender_name=membre.nom_complet,
        scope=scope,
        direction='out',
        thread_id=thread_id,
        subject=subject,
        message=message,
        target_membre_id=data.get('target_membre_id'),
        target_cellule_id=data.get('target_cellule_id'),
        target_type_membre_id=data.get('target_type_membre_id'),
        target_group_id=data.get('target_group_id'),
        status='sent',
    )

    return JsonResponse({
        'success': True,
        'message_id': comm.id,
        'time': comm.created_at.strftime('%H:%M'),
    })


# ============================================================
# API COMMUNICATION — CREATE GROUP
# ============================================================
@csrf_exempt
@require_POST
def api_communication_group_create(request):
    """Crée un groupe de communication."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    nom = data.get('nom', '').strip()
    if not nom:
        return JsonResponse({'success': False, 'error': 'Nom requis'})

    grp = CommunicationGroupe.objects.create(
        nom=nom,
        description=data.get('description', ''),
        createur=membre,
        couleur_avatar=data.get('couleur', '#1a3a5c'),
    )

    # Ajouter le créateur comme membre
    CommunicationGroupeMembre.objects.create(groupe=grp, membre=membre)

    # Ajouter les membres sélectionnés
    for mid in data.get('membres', []):
        try:
            m = Membre.objects.get(id=mid, est_actif=True)
            CommunicationGroupeMembre.objects.get_or_create(groupe=grp, membre=m)
        except Membre.DoesNotExist:
            pass

    count = grp.membres_groupe.count()
    return JsonResponse({
        'success': True,
        'group': {
            'id': grp.id, 'nom': grp.nom, 'couleur': grp.couleur_avatar,
            'count': count,
        }
    })


# ============================================================
# API COMMUNICATION — DELETE GROUP
# ============================================================
@csrf_exempt
@require_POST
def api_communication_group_delete(request):
    """Supprime un groupe (créateur uniquement)."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    try:
        grp = CommunicationGroupe.objects.get(id=data.get('id'), createur=membre)
        grp.delete()
        return JsonResponse({'success': True, 'message': 'Groupe supprimé.'})
    except CommunicationGroupe.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Groupe introuvable ou accès refusé'})


# ============================================================
# API COMMUNICATION — SEND WITH ATTACHMENT
# ============================================================
@csrf_exempt
@require_POST
def api_communication_send_file(request):
    """Envoie un message avec pièce jointe (FormData)."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    thread_id = request.POST.get('thread_id', '')
    message = request.POST.get('message', '').strip()
    scope = request.POST.get('scope', 'individual')
    subject = request.POST.get('subject', '')
    uploaded = request.FILES.get('attachment')

    if not message and not uploaded:
        return JsonResponse({'success': False, 'error': 'Message ou fichier requis'})

    att_name = None
    att_type = None
    att_file = None
    if uploaded:
        att_name = uploaded.name
        ext = uploaded.name.rsplit('.', 1)[-1].lower() if '.' in uploaded.name else ''
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            att_type = 'image'
        elif ext == 'pdf':
            att_type = 'pdf'
        elif ext in ('doc', 'docx', 'odt'):
            att_type = 'document'
        else:
            att_type = 'file'
        att_file = uploaded

    comm = Communication.objects.create(
        sender=membre,
        sender_name=membre.nom_complet,
        scope=scope,
        direction='out',
        thread_id=thread_id,
        subject=subject,
        message=message or f'📎 {att_name}',
        target_membre_id=request.POST.get('target_membre_id') or None,
        target_cellule_id=request.POST.get('target_cellule_id') or None,
        target_type_membre_id=request.POST.get('target_type_membre_id') or None,
        target_group_id=request.POST.get('target_group_id') or None,
        attachment=att_file,
        attachment_name=att_name,
        attachment_type=att_type,
        status='sent',
    )

    att_data = None
    if comm.attachment:
        att_data = {'url': comm.attachment.url, 'name': att_name, 'type': att_type}

    return JsonResponse({
        'success': True,
        'message_id': comm.id,
        'time': comm.created_at.strftime('%H:%M'),
        'attachment': att_data,
    })


# ============================================================
# API COMMUNICATION — UNREAD COUNT (pour badge sidebar/topbar)
# ============================================================
@csrf_exempt
def api_communication_unread(request):
    """Retourne le nombre de messages non lus pour le badge."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'count': 0})

    # Messages individuels non lus
    individual_unread = Communication.objects.filter(
        target_membre=membre, is_read=False
    ).exclude(sender=membre).count()

    # Messages dans les threads de groupes/national/cellule
    group_threads = set()
    group_threads.add('national')
    group_threads.add('general')
    if membre.cellule_id:
        group_threads.add(f'cell_{membre.cellule_id}')
    # Groupes personnalisés
    grp_ids = CommunicationGroupeMembre.objects.filter(
        membre=membre
    ).values_list('groupe_id', flat=True)
    for gid in grp_ids:
        group_threads.add(f'cgrp_{gid}')

    group_unread = Communication.objects.filter(
        thread_id__in=group_threads, is_read=False
    ).exclude(sender=membre).count()

    total = individual_unread + group_unread
    return JsonResponse({'success': True, 'count': total})


# ============================================================
# API COMMUNICATION — VISIO (Jitsi Meet)
# ============================================================
@csrf_exempt
def api_communication_visio(request):
    """Génère un room Jitsi pour un appel direct."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    import uuid as uuid_module
    thread_id = request.GET.get('thread_id', '')
    contact_name = request.GET.get('contact_name', 'Réunion')

    room_suffix = uuid_module.uuid4().hex[:10]
    room_name = f"SEBC-{thread_id.replace('_', '-')}-{room_suffix}"
    # Nettoyer le nom de room (Jitsi n'aime pas certains caractères)
    room_name = ''.join(c for c in room_name if c.isalnum() or c == '-')

    share_link = f"https://meet.jit.si/{room_name}"

    return JsonResponse({
        'success': True,
        'room_name': room_name,
        'jitsi_url': share_link,
        'share_link': share_link,
        'display_name': membre.nom_complet,
        'subject': f"Appel : {contact_name}",
    })


# ============================================================
# API MEETINGS — CREATE
# ============================================================
@csrf_exempt
@require_POST
def api_meeting_create(request):
    """Planifie une réunion."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    title = data.get('title', '').strip()
    if not title:
        return JsonResponse({'success': False, 'error': 'Titre requis'})

    scheduled_at = data.get('scheduled_at', '')
    if not scheduled_at:
        return JsonResponse({'success': False, 'error': 'Date requise'})

    import uuid as uuid_module
    from datetime import datetime
    room_suffix = uuid_module.uuid4().hex[:12]
    room_name = f"SEBC-{title[:20].replace(' ', '-')}-{room_suffix}"
    room_name = ''.join(c for c in room_name if c.isalnum() or c == '-')
    join_token = uuid_module.uuid4().hex

    try:
        sched_dt = datetime.fromisoformat(scheduled_at)
        sched_dt = timezone.make_aware(sched_dt) if timezone.is_naive(sched_dt) else sched_dt
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Date invalide'})

    meeting = Meeting.objects.create(
        title=title,
        description=data.get('description', ''),
        room_name=room_name,
        join_token=join_token,
        created_by=membre,
        scheduled_at=sched_dt,
        duration_minutes=int(data.get('duration_minutes', 60)),
    )

    # Invitations
    invitees = data.get('invitees', [])
    for mid in invitees:
        try:
            m = Membre.objects.get(id=mid, est_actif=True)
            MeetingInvite.objects.create(meeting=meeting, membre=m)
        except Membre.DoesNotExist:
            pass

    # Notification email aux invités
    try:
        from .email_service import send_brevo_email
        invite_emails = list(Membre.objects.filter(id__in=invitees, est_actif=True).values_list('email', flat=True))
        if invite_emails:
            send_brevo_email(
                to_emails=invite_emails,
                subject=f'[SEBC] Réunion : {title}',
                html_content=f"""
                <h2>📹 Nouvelle réunion planifiée</h2>
                <p><strong>{title}</strong></p>
                <p>📅 {scheduled_at}</p>
                <p>⏱ {meeting.duration_minutes} minutes</p>
                <p>Organisé par : {membre.nom_complet}</p>
                <p><a href="{meeting.share_url}" style="background:#1a3a5c;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;display:inline-block;margin-top:10px">
                    📹 Rejoindre la réunion
                </a></p>
                """
            )
    except Exception as e:
        logger.error(f"Erreur notification meeting: {e}")

    return JsonResponse({
        'success': True,
        'meeting': {
            'id': meeting.id,
            'title': meeting.title,
            'room_name': meeting.room_name,
            'share_url': meeting.share_url,
            'scheduled_at': scheduled_at,
            'duration_minutes': meeting.duration_minutes,
            'created_by_name': membre.nom_complet,
        }
    })


# ============================================================
# API MEETINGS — LIST
# ============================================================
@csrf_exempt
def api_meeting_list(request):
    """Liste des réunions du membre."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    # Réunions créées par ou auxquelles invité
    meetings = Meeting.objects.filter(
        Q(created_by=membre) | Q(invites__membre=membre)
    ).distinct().order_by('-scheduled_at')[:50]

    meetings_data = []
    for m in meetings:
        meetings_data.append({
            'id': m.id,
            'title': m.title,
            'description': m.description,
            'room_name': m.room_name,
            'share_url': m.share_url,
            'status': m.status,
            'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else '',
            'scheduled_display': m.scheduled_at.strftime('%d/%m/%Y %H:%M') if m.scheduled_at else '',
            'duration_minutes': m.duration_minutes,
            'n_invitees': m.invites.count(),
            'is_owner': m.created_by_id == membre.id,
            'creator_name': f"{m.created_by.prenom} {m.created_by.nom}" if m.created_by else '',
        })

    return JsonResponse({'success': True, 'meetings': meetings_data})


# ============================================================
# API MEETINGS — CANCEL
# ============================================================
@csrf_exempt
@require_POST
def api_meeting_cancel(request):
    """Annule une réunion (créateur uniquement)."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'})

    try:
        meeting = Meeting.objects.get(id=data.get('id'), created_by=membre)
        meeting.status = 'cancelled'
        meeting.save(update_fields=['status'])
        return JsonResponse({'success': True, 'message': 'Réunion annulée.'})
    except Meeting.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Réunion introuvable'})


# ============================================================
# API MEETINGS — JOIN BY TOKEN
# ============================================================
@csrf_exempt
def api_meeting_join(request):
    """Rejoint une réunion via token."""
    membre = _get_logged_membre(request)
    if not membre:
        return JsonResponse({'success': False, 'error': 'Non connecté'}, status=401)

    token = request.GET.get('token', '')
    try:
        meeting = Meeting.objects.get(join_token=token)
        if meeting.status == 'cancelled':
            return JsonResponse({'success': False, 'error': 'Cette réunion a été annulée.'})
        return JsonResponse({
            'success': True,
            'meeting': {
                'id': meeting.id,
                'title': meeting.title,
                'room_name': meeting.room_name,
            },
            'display_name': membre.nom_complet,
        })
    except Meeting.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Réunion introuvable'})
