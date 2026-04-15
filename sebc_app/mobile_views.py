"""
SEBC Mobile API — Endpoints dédiés à l'application Flutter
Authentification par token (X-Session-Token header ou session Django)
"""
import json
import uuid
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Count, Q

from .models import (
    Membre, TypeAyantDroit, AyantDroit, Cellule, Pays,
    ParametreAssociation, Province, TypeSoutien,
    Module, AccesModule,
    TypeMembre, Communication, CommunicationGroupe, CommunicationGroupeMembre,
    Meeting, MeetingInvite
)
from .email_service import send_otp_email

logger = logging.getLogger(__name__)


# ============================================================
# HELPER — Auth mobile par token
# ============================================================
def _get_mobile_membre(request):
    """Récupère le membre connecté via X-Session-Token header ou session Django."""
    # 1) Header token
    token = request.headers.get('X-Session-Token', request.GET.get('token', ''))
    if token:
        try:
            return Membre.objects.get(mobile_token=token, est_actif=True)
        except Membre.DoesNotExist:
            pass
    # 2) Session Django (fallback)
    membre_id = request.session.get('membre_id')
    if membre_id:
        try:
            return Membre.objects.get(id=membre_id, est_actif=True)
        except Membre.DoesNotExist:
            pass
    return None


def _membre_to_dict(m):
    """Serialize un membre en dictionnaire."""
    type_m = None
    if m.type_membre:
        type_m = f"{m.type_membre.libelle}"
        if m.type_membre.niveau:
            type_m += f" ({m.type_membre.niveau})"
    return {
        'id': m.id,
        'nom': m.nom,
        'prenom': m.prenom,
        'email': m.email,
        'telephone': m.telephone_whatsapp,
        'telephone_canada': m.telephone_canada,
        'ville': m.ville_residence,
        'cellule_code': m.cellule.code if m.cellule else None,
        'cellule_nom': m.cellule.nom if m.cellule else None,
        'type_membre': type_m,
        'statut': m.statut,
        'role': m.role,
        'est_actif': m.est_actif,
        'is_gestionnaire': m.is_gestionnaire(),
        'province_origine': m.province_origine,
    }


def _auth_required(view_func):
    """Décorateur pour vérifier l'auth mobile."""
    def wrapper(request, *args, **kwargs):
        membre = _get_mobile_membre(request)
        if not membre:
            return JsonResponse({'success': False, 'error': 'Non authentifié', 'auth_required': True}, status=401)
        request.membre = membre
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ============================================================
# AUTH
# ============================================================
@csrf_exempt
@require_POST
def mobile_check_email(request):
    """Vérifie si un email existe."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})
    exists = Membre.objects.filter(email=email, est_actif=True).exists()
    return JsonResponse({'success': True, 'exists': exists})


@csrf_exempt
@require_POST
def mobile_login(request):
    """Connexion mobile — retourne un token."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        password = data.get('mot_de_passe', '') or data.get('password', '')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    try:
        membre = Membre.objects.get(email=email, est_actif=True)
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Email non reconnu.'})

    if not membre.email_verifie:
        return JsonResponse({'success': False, 'error': 'Email non vérifié.'})

    if not membre.check_password(password):
        return JsonResponse({'success': False, 'error': 'Mot de passe incorrect.'})

    # Générer token mobile
    token = uuid.uuid4().hex
    membre.mobile_token = token
    membre.derniere_connexion = timezone.now()
    membre.save(update_fields=['mobile_token', 'derniere_connexion'])

    return JsonResponse({
        'success': True,
        'session_token': token,
        'membre': _membre_to_dict(membre),
    })


@csrf_exempt
@require_POST
def mobile_request_otp(request):
    """Envoie un code OTP par email."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})
    try:
        membre = Membre.objects.get(email=email, est_actif=True)
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Email non trouvé.'})
    otp_code = membre.generate_otp(otp_type='EMAIL')
    result = send_otp_email(email, otp_code, membre.prenom)
    if result.get('success'):
        return JsonResponse({'success': True, 'message': 'Code envoyé par email.'})
    return JsonResponse({'success': False, 'error': "Erreur d'envoi."})


@csrf_exempt
@require_POST
def mobile_verify_otp(request):
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
        membre.email_verifie = True
        membre.save(update_fields=['email_verifie'])
        return JsonResponse({'success': True, 'token': str(membre.uuid)})
    return JsonResponse({'success': False, 'error': 'Code incorrect ou expiré.'})


@csrf_exempt
@require_POST
def mobile_set_password(request):
    """Définit le mot de passe après vérification OTP."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        password = data.get('mot_de_passe', '') or data.get('password', '')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})
    if len(password) < 6:
        return JsonResponse({'success': False, 'error': 'Minimum 6 caractères.'})
    try:
        membre = Membre.objects.get(email=email, est_actif=True)
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Email non trouvé.'})
    membre.set_password(password)
    token = uuid.uuid4().hex
    membre.mobile_token = token
    membre.save(update_fields=['mot_de_passe_hash', 'mobile_token'])
    return JsonResponse({'success': True, 'session_token': token, 'membre': _membre_to_dict(membre)})


@csrf_exempt
@require_POST
def mobile_logout(request):
    """Déconnexion mobile — invalide le token."""
    membre = _get_mobile_membre(request)
    if membre:
        membre.mobile_token = None
        membre.save(update_fields=['mobile_token'])
    return JsonResponse({'success': True})


# ============================================================
# CANDIDATURE
# ============================================================
@csrf_exempt
@require_POST
def mobile_check_parrain(request):
    """Vérifie si un parrain existe."""
    try:
        data = json.loads(request.body)
        contact = data.get('email_ou_telephone', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    parrain = Membre.objects.filter(
        Q(email=contact.lower()) | Q(telephone_whatsapp=contact) | Q(telephone_canada=contact),
        statut='APPROUVE', est_actif=True
    ).first()

    if parrain:
        return JsonResponse({
            'success': True, 'found': True,
            'parrain_id': parrain.id,
            'email': parrain.email,
        })
    return JsonResponse({'success': True, 'found': False, 'error': 'Parrain non trouvé.'})


@csrf_exempt
@require_POST
def mobile_submit_candidature(request):
    """Soumission d'une candidature d'adhésion depuis l'app mobile."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    for field in ['nom', 'prenom', 'email', 'telephone_whatsapp']:
        if not data.get(field, '').strip():
            return JsonResponse({'success': False, 'error': f'Le champ {field} est obligatoire.'})

    email = data['email'].strip().lower()
    if Membre.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Un compte existe déjà avec cet email.'})

    try:
        parrain = None
        if data.get('parrain_id'):
            parrain = Membre.objects.filter(id=data['parrain_id'], statut='APPROUVE', est_actif=True).first()

        membre = Membre.objects.create(
            nom=data['nom'].strip().upper(),
            prenom=data['prenom'].strip().title(),
            email=email,
            telephone_whatsapp=data['telephone_whatsapp'].strip(),
            telephone_canada=data.get('telephone_canada', '').strip() or None,
            ville_residence=data.get('ville', '').strip() or None,
            personne_referante=parrain,
            nom_personne_referante=parrain.nom_complet if parrain else None,
            tel_personne_referante=parrain.telephone_whatsapp if parrain else None,
            email_personne_referante=parrain.email if parrain else None,
            statut='EN_ATTENTE',
        )

        # Envoyer OTP
        otp_code = membre.generate_otp(otp_type='EMAIL')
        send_otp_email(email, otp_code, membre.prenom)

        # Notifier le parrain
        if parrain:
            from .email_service import send_brevo_email
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
        <p style="color:#333;font-size:15px;line-height:1.6;margin:0 0 16px"><strong>{membre.prenom} {membre.nom}</strong> vient de soumettre une demande d'adhésion en vous désignant comme parrain via l'application mobile.</p>
        <div style="background:#f0f7ff;border-left:4px solid #1a3a5c;padding:14px 18px;border-radius:0 8px 8px 0;margin:16px 0">
            <p style="margin:0;font-size:14px;color:#1a3a5c"><strong>Candidat :</strong> {membre.prenom} {membre.nom}</p>
            <p style="margin:4px 0 0;font-size:14px;color:#1a3a5c"><strong>Email :</strong> {membre.email}</p>
            <p style="margin:4px 0 0;font-size:14px;color:#1a3a5c"><strong>Téléphone :</strong> {membre.telephone_whatsapp}</p>
        </div>
        <p style="color:#333;font-size:15px;line-height:1.6;margin:16px 0">Connectez-vous à votre espace pour <strong>valider ou non</strong> ce parrainage :</p>
        <div style="text-align:center;margin:20px 0">
            <a href="https://sebc-dushigikirane.pro/login/" style="display:inline-block;background:linear-gradient(135deg,#1a3a5c,#2c5f8a);color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px">Accéder à mon espace</a>
        </div>
    </td></tr>
    <tr><td style="background:#f8f9fa;padding:12px 30px;text-align:center">
        <p style="color:#aaa;font-size:11px;margin:0">&copy; S.E.B.C Dushigikirane</p>
    </td></tr>
</table>
</td></tr></table></body></html>"""
            send_brevo_email(
                to_emails=[parrain.email],
                subject=f'[SEBC] Nouveau filleul : {membre.prenom} {membre.nom} demande votre parrainage',
                html_content=parrain_html,
            )

        return JsonResponse({'success': True, 'message': 'Candidature soumise ! Vérifiez votre email.', 'membre_id': membre.id})
    except Exception as e:
        logger.error(f"Erreur candidature mobile: {e}")
        return JsonResponse({'success': False, 'error': 'Erreur lors de la soumission.'})


# ============================================================
# PROFIL MEMBRE
# ============================================================
@csrf_exempt
@_auth_required
def mobile_profile(request):
    """Retourne le profil complet du membre connecté avec filleuls en attente."""
    m = request.membre
    data = _membre_to_dict(m)

    # Filleuls en attente de validation
    filleuls = Membre.objects.filter(
        personne_referante=m, statut='EN_ATTENTE', parrain_valide=False
    ).values('id', 'nom', 'prenom', 'email', 'telephone_whatsapp')
    data['filleuls_en_attente'] = list(filleuls)

    # Statut de parrainage (si je suis en attente)
    data['parrain_valide'] = m.parrain_valide
    data['parrain_nom'] = m.nom_personne_referante

    return JsonResponse({'success': True, 'membre': data})


@csrf_exempt
@require_POST
@_auth_required
def mobile_update_profile(request):
    """Met à jour le profil du membre."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    m = request.membre
    for field in ['telephone_whatsapp', 'telephone_canada', 'ville_residence', 'province_origine']:
        if field in data:
            setattr(m, field, data[field].strip() if data[field] else None)
    m.save()
    return JsonResponse({'success': True, 'membre': _membre_to_dict(m)})


@csrf_exempt
@_auth_required
def mobile_ayants_droits(request):
    """Liste les ayants droits du membre connecté."""
    ads = AyantDroit.objects.filter(membre=request.membre).select_related('type_lien')
    data = [{
        'id': ad.id,
        'nom': ad.nom,
        'prenom': ad.prenom,
        'type_lien': ad.type_lien.libelle if ad.type_lien else '',
        'est_approuve': ad.est_approuve,
    } for ad in ads]
    return JsonResponse({'success': True, 'ayants_droits': data})


@csrf_exempt
@require_POST
@_auth_required
def mobile_valider_filleul(request):
    """Valide un filleul en tant que parrain."""
    try:
        data = json.loads(request.body)
        filleul_id = data.get('filleul_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    try:
        filleul = Membre.objects.get(id=filleul_id, personne_referante=request.membre)
    except Membre.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Filleul non trouvé.'})

    filleul.parrain_valide = True
    filleul.save(update_fields=['parrain_valide'])

    # Notifier le filleul
    from .email_service import send_brevo_email
    send_brevo_email(
        to_emails=[filleul.email],
        subject='[SEBC] Votre parrainage a été validé !',
        html_content=f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:20px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden">
    <tr><td style="background:linear-gradient(135deg,#059669,#10b981);padding:24px 30px;text-align:center">
        <h1 style="color:#fff;margin:0;font-size:22px">✅ Parrainage Validé</h1>
    </td></tr>
    <tr><td style="padding:30px">
        <p style="color:#333;font-size:15px">Bonjour {filleul.prenom},</p>
        <p style="color:#333;font-size:15px;line-height:1.6">Bonne nouvelle ! <strong>{request.membre.prenom} {request.membre.nom}</strong> a validé votre parrainage.</p>
        <p style="color:#333;font-size:15px;line-height:1.6">Votre candidature continue son processus d'approbation.</p>
        <div style="text-align:center;margin:20px 0">
            <a href="https://sebc-dushigikirane.pro/login/" style="display:inline-block;background:linear-gradient(135deg,#1a3a5c,#2c5f8a);color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700">Se connecter</a>
        </div>
    </td></tr>
    <tr><td style="background:#f8f9fa;padding:12px;text-align:center"><p style="color:#aaa;font-size:11px;margin:0">&copy; SEBC</p></td></tr>
</table></td></tr></table></body></html>"""
    )

    return JsonResponse({'success': True, 'message': 'Parrainage validé !'})


@csrf_exempt
@require_POST
@_auth_required
def mobile_relancer_parrain(request):
    """Relance le parrain par email."""
    m = request.membre
    if not m.personne_referante:
        return JsonResponse({'success': False, 'error': 'Aucun parrain associé.'})
    if m.parrain_valide:
        return JsonResponse({'success': False, 'error': 'Parrainage déjà validé.'})

    parrain = m.personne_referante
    from .email_service import send_brevo_email
    send_brevo_email(
        to_emails=[parrain.email],
        subject=f'[SEBC] Rappel : {m.prenom} {m.nom} attend votre validation',
        html_content=f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:20px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden">
    <tr><td style="background:linear-gradient(135deg,#d97706,#f59e0b);padding:24px 30px;text-align:center">
        <h1 style="color:#fff;margin:0;font-size:22px">⏰ Rappel de Parrainage</h1>
    </td></tr>
    <tr><td style="padding:30px">
        <p style="color:#333;font-size:15px">Bonjour {parrain.prenom},</p>
        <p style="color:#333;font-size:15px;line-height:1.6"><strong>{m.prenom} {m.nom}</strong> attend toujours votre validation de parrainage. Connectez-vous pour valider :</p>
        <div style="text-align:center;margin:20px 0">
            <a href="https://sebc-dushigikirane.pro/login/" style="display:inline-block;background:linear-gradient(135deg,#1a3a5c,#2c5f8a);color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700">Valider le parrainage</a>
        </div>
    </td></tr>
    <tr><td style="background:#f8f9fa;padding:12px;text-align:center"><p style="color:#aaa;font-size:11px;margin:0">&copy; SEBC</p></td></tr>
</table></td></tr></table></body></html>"""
    )
    return JsonResponse({'success': True, 'message': 'Relance envoyée au parrain.'})


# ============================================================
# COMMUNICATION
# ============================================================
@csrf_exempt
@_auth_required
def mobile_comm_contacts(request):
    """Liste des contacts pour la messagerie."""
    membre = request.membre
    data = {'success': True, 'cellules': [], 'custom_groups': [], 'types_membres': [], 'members': []}

    # Cellules
    for c in Cellule.objects.filter(est_actif=True):
        count = Membre.objects.filter(cellule=c, est_actif=True).count()
        data['cellules'].append({'id': c.id, 'code': c.code, 'nom': c.nom, 'count': count})

    # Custom groups
    my_groups = CommunicationGroupeMembre.objects.filter(membre=membre).values_list('groupe_id', flat=True)
    for g in CommunicationGroupe.objects.filter(Q(id__in=my_groups) | Q(created_by=membre)):
        count = CommunicationGroupeMembre.objects.filter(groupe=g).count()
        data['custom_groups'].append({'id': g.id, 'nom': g.nom, 'count': count})

    # Types membres
    for t in TypeMembre.objects.all():
        count = Membre.objects.filter(type_membre=t, est_actif=True).count()
        data['types_membres'].append({'id': t.id, 'libelle': t.libelle, 'count': count})

    # All members
    for m in Membre.objects.filter(est_actif=True).exclude(id=membre.id).order_by('prenom', 'nom'):
        data['members'].append({'id': m.id, 'nom_complet': m.nom_complet, 'email': m.email})

    return JsonResponse(data)


@csrf_exempt
@_auth_required
def mobile_comm_threads(request):
    """Liste des threads avec dernier message et compteur non-lu."""
    membre = request.membre
    threads = Communication.objects.filter(
        Q(sender=membre) | Q(target_membre=membre) | Q(scope='national') |
        Q(scope='cellule', target_cellule=membre.cellule) |
        Q(scope='custom_group', target_group__in=CommunicationGroupeMembre.objects.filter(membre=membre).values_list('groupe_id', flat=True))
    ).values('thread_id').annotate(
        total=Count('id'),
        unread=Count('id', filter=Q(is_read=False) & ~Q(sender=membre))
    ).order_by('-thread_id')

    results = []
    for t in threads:
        last_msg = Communication.objects.filter(thread_id=t['thread_id']).order_by('-created_at').first()
        results.append({
            'thread_id': t['thread_id'],
            'last_message': (last_msg.message[:50] if last_msg and last_msg.message else '') if last_msg else '',
            'last_time': last_msg.created_at.strftime('%H:%M') if last_msg and last_msg.created_at else '',
            'unread': t['unread'],
        })
    return JsonResponse({'success': True, 'threads': results})


@csrf_exempt
@_auth_required
def mobile_comm_messages(request):
    """Messages d'un thread."""
    thread_id = request.GET.get('thread_id', '')
    membre = request.membre

    msgs = Communication.objects.filter(thread_id=thread_id).order_by('created_at')[:200]
    # Marquer comme lus
    Communication.objects.filter(thread_id=thread_id, is_read=False).exclude(sender=membre).update(is_read=True, read_at=timezone.now())

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


@csrf_exempt
@require_POST
@_auth_required
def mobile_comm_send(request):
    """Envoyer un message texte."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    membre = request.membre
    thread_id = data.get('thread_id', '')
    scope = data.get('scope', 'individual')
    message = data.get('message', '').strip()

    if not message and not thread_id:
        return JsonResponse({'success': False, 'error': 'Message vide.'})

    comm = Communication.objects.create(
        thread_id=thread_id,
        sender=membre,
        sender_name=membre.nom_complet,
        scope=scope,
        message=message,
        subject=data.get('subject'),
        target_membre_id=data.get('target_membre_id'),
        target_cellule_id=data.get('target_cellule_id'),
        target_group_id=data.get('target_group_id'),
        target_type_membre_id=data.get('target_type_membre_id'),
    )
    return JsonResponse({'success': True, 'message_id': comm.id})


@csrf_exempt
@require_POST
@_auth_required
def mobile_comm_send_file(request):
    """Envoyer un message avec fichier attaché."""
    membre = request.membre
    thread_id = request.POST.get('thread_id', '')
    scope = request.POST.get('scope', 'individual')
    message = request.POST.get('message', '')
    attachment = request.FILES.get('attachment')

    if not attachment and not message.strip():
        return JsonResponse({'success': False, 'error': 'Rien à envoyer.'})

    att_type = 'file'
    if attachment:
        ext = attachment.name.lower().split('.')[-1] if '.' in attachment.name else ''
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            att_type = 'image'
        elif ext == 'pdf':
            att_type = 'pdf'
        elif ext in ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx']:
            att_type = 'document'

    comm = Communication.objects.create(
        thread_id=thread_id,
        sender=membre,
        sender_name=membre.nom_complet,
        scope=scope,
        message=message,
        attachment=attachment,
        attachment_name=attachment.name if attachment else None,
        attachment_type=att_type,
        target_membre_id=request.POST.get('target_membre_id') or None,
        target_cellule_id=request.POST.get('target_cellule_id') or None,
        target_group_id=request.POST.get('target_group_id') or None,
    )
    return JsonResponse({'success': True, 'message_id': comm.id})


@csrf_exempt
@_auth_required
def mobile_comm_unread(request):
    """Compteur total de messages non lus."""
    membre = request.membre
    count = Communication.objects.filter(
        Q(target_membre=membre) | Q(scope='national') | Q(scope='cellule', target_cellule=membre.cellule),
        is_read=False
    ).exclude(sender=membre).count()
    return JsonResponse({'success': True, 'count': count})


@csrf_exempt
@_auth_required
def mobile_comm_visio(request):
    """Génère un lien de visioconférence Jitsi."""
    thread_id = request.GET.get('thread_id', '')
    contact_name = request.GET.get('contact_name', 'Réunion')
    room_name = f"SEBC-{thread_id}-{uuid.uuid4().hex[:8]}"
    jitsi_url = f"https://meet.jit.si/{room_name}"
    share_link = f"https://sebc-dushigikirane.pro/communication/?join={room_name}"
    return JsonResponse({'success': True, 'room_name': room_name, 'jitsi_url': jitsi_url, 'share_link': share_link})


@csrf_exempt
@require_POST
@_auth_required
def mobile_comm_group_create(request):
    """Créer un groupe personnalisé."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    nom = data.get('nom', '').strip()
    if not nom:
        return JsonResponse({'success': False, 'error': 'Le nom du groupe est obligatoire.'})

    groupe = CommunicationGroupe.objects.create(
        nom=nom,
        description=data.get('description', ''),
        couleur=data.get('couleur', '#1a3a5c'),
        created_by=request.membre,
    )
    # Ajouter le créateur
    CommunicationGroupeMembre.objects.create(groupe=groupe, membre=request.membre)
    # Ajouter les membres
    for mid in data.get('membres', []):
        try:
            m = Membre.objects.get(id=mid, est_actif=True)
            CommunicationGroupeMembre.objects.get_or_create(groupe=groupe, membre=m)
        except Membre.DoesNotExist:
            pass
    return JsonResponse({'success': True, 'group_id': groupe.id})


@csrf_exempt
@require_POST
@_auth_required
def mobile_comm_group_delete(request):
    """Supprimer un groupe personnalisé."""
    try:
        data = json.loads(request.body)
        group_id = data.get('id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    try:
        groupe = CommunicationGroupe.objects.get(id=group_id, created_by=request.membre)
        groupe.delete()
        return JsonResponse({'success': True})
    except CommunicationGroupe.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Groupe non trouvé ou non autorisé.'})


# ============================================================
# MEETINGS
# ============================================================
@csrf_exempt
@_auth_required
def mobile_meeting_list(request):
    """Liste des réunions."""
    membre = request.membre
    meetings = Meeting.objects.filter(
        Q(creator=membre) | Q(invitees__membre=membre)
    ).distinct().order_by('-scheduled_at')

    data = []
    for m in meetings:
        data.append({
            'id': m.id,
            'title': m.title,
            'description': m.description,
            'room_name': m.room_name,
            'share_url': f'https://sebc-dushigikirane.pro/communication/?join={m.join_token}',
            'status': m.status,
            'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else '',
            'scheduled_display': m.scheduled_at.strftime('%d/%m/%Y %H:%M') if m.scheduled_at else '',
            'duration_minutes': m.duration_minutes,
            'n_invitees': m.invitees.count(),
            'is_owner': m.creator_id == membre.id,
            'creator_name': m.creator.nom_complet if m.creator else '',
        })
    return JsonResponse({'success': True, 'meetings': data})


@csrf_exempt
@require_POST
@_auth_required
def mobile_meeting_create(request):
    """Planifier une réunion."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    title = data.get('title', '').strip()
    if not title:
        return JsonResponse({'success': False, 'error': 'Le titre est obligatoire.'})

    room_name = f"SEBC-{uuid.uuid4().hex[:12]}"
    join_token = uuid.uuid4().hex

    meeting = Meeting.objects.create(
        title=title,
        description=data.get('description', ''),
        room_name=room_name,
        join_token=join_token,
        creator=request.membre,
        scheduled_at=data.get('scheduled_at'),
        duration_minutes=data.get('duration_minutes', 60),
        status='scheduled',
    )

    share_url = f'https://sebc-dushigikirane.pro/communication/?join={join_token}'

    # Inviter les participants
    from .email_service import send_brevo_email
    for mid in data.get('invitees', []):
        try:
            m = Membre.objects.get(id=mid, est_actif=True)
            MeetingInvite.objects.create(meeting=meeting, membre=m)
            # Notification email
            send_brevo_email(
                to_emails=[m.email],
                subject=f'[SEBC] Invitation : {title}',
                html_content=f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:20px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden">
    <tr><td style="background:linear-gradient(135deg,#0d9488,#14b8a6);padding:24px 30px;text-align:center">
        <h1 style="color:#fff;margin:0;font-size:22px">📅 Invitation à une réunion</h1>
    </td></tr>
    <tr><td style="padding:30px">
        <p style="color:#333;font-size:15px">Bonjour {m.prenom},</p>
        <p style="color:#333;font-size:15px;line-height:1.6"><strong>{request.membre.nom_complet}</strong> vous invite à la réunion :</p>
        <div style="background:#f0f7ff;border-left:4px solid #0d9488;padding:14px 18px;border-radius:0 8px 8px 0;margin:16px 0">
            <p style="margin:0;font-size:15px;font-weight:700;color:#1a3a5c">{title}</p>
            <p style="margin:4px 0 0;font-size:14px;color:#64748b">{meeting.description or ''}</p>
        </div>
        <div style="text-align:center;margin:20px 0">
            <a href="{share_url}" style="display:inline-block;background:linear-gradient(135deg,#0d9488,#14b8a6);color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px">Rejoindre la réunion</a>
        </div>
    </td></tr>
    <tr><td style="background:#f8f9fa;padding:12px;text-align:center"><p style="color:#aaa;font-size:11px;margin:0">&copy; SEBC</p></td></tr>
</table></td></tr></table></body></html>"""
            )
        except Membre.DoesNotExist:
            pass

    return JsonResponse({
        'success': True,
        'meeting': {
            'id': meeting.id,
            'title': meeting.title,
            'room_name': room_name,
            'share_url': share_url,
            'scheduled_at': str(meeting.scheduled_at),
            'duration_minutes': meeting.duration_minutes,
        }
    })


@csrf_exempt
@require_POST
@_auth_required
def mobile_meeting_cancel(request):
    """Annuler une réunion."""
    try:
        data = json.loads(request.body)
        meeting_id = data.get('id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide'})

    try:
        meeting = Meeting.objects.get(id=meeting_id, creator=request.membre)
        meeting.status = 'cancelled'
        meeting.save(update_fields=['status'])
        return JsonResponse({'success': True})
    except Meeting.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Réunion non trouvée.'})


@csrf_exempt
@_auth_required
def mobile_meeting_join(request):
    """Rejoindre une réunion par token."""
    token = request.GET.get('token', '')
    try:
        meeting = Meeting.objects.get(join_token=token)
        jitsi_url = f"https://meet.jit.si/{meeting.room_name}"
        return JsonResponse({'success': True, 'jitsi_url': jitsi_url, 'title': meeting.title, 'room_name': meeting.room_name})
    except Meeting.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Réunion non trouvée.'})


# ============================================================
# DONNÉES DE RÉFÉRENCE
# ============================================================
@csrf_exempt
def mobile_ref_data(request):
    """Retourne les données de référence pour les formulaires."""
    pays = [{'id': p.id, 'nom': p.nom, 'code': p.code_iso} for p in Pays.objects.filter(est_actif=True).order_by('nom')]
    provinces = [{'id': p.id, 'nom': p.nom, 'pays_id': p.pays_id} for p in Province.objects.all().order_by('nom')]
    cellules = [{'id': c.id, 'code': c.code, 'nom': c.nom} for c in Cellule.objects.filter(est_actif=True)]
    types_ad = [{'id': t.id, 'libelle': t.libelle} for t in TypeAyantDroit.objects.filter(est_actif=True)]

    return JsonResponse({'success': True, 'pays': pays, 'provinces': provinces, 'cellules': cellules, 'types_ayants_droits': types_ad})
