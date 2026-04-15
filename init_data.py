"""
Script d'initialisation des données de base SEBC.
Lancer avec: python manage.py shell < init_data.py
   ou bien: python init_data.py (si DJANGO_SETTINGS_MODULE est défini)
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SEBC.settings')
django.setup()

from sebc_app.models import (
    TypeAyantDroit, Pays, Cellule, Membre,
    ParametreAssociation, Province, TypeSoutien,
    Module, AccesModule, TypeMembre
)

# 1. Types d'ayants droits
types = ['Père', 'Mère', 'Époux/Épouse', 'Fils/Fille', 'Frère/Sœur', 'Beau-père/Belle-mère']
for t in types:
    TypeAyantDroit.objects.get_or_create(libelle=t)
print(f'✅ Types ayants droits: {TypeAyantDroit.objects.count()}')

# 2. Pays
pays_data = [
    ('Canada', 'CAN', '+1'),
    ('Burundi', 'BDI', '+257'),
    ('France', 'FRA', '+33'),
    ('Belgique', 'BEL', '+32'),
    ('États-Unis', 'USA', '+1'),
]
for nom, code, indic in pays_data:
    Pays.objects.get_or_create(nom=nom, defaults={'code_iso': code, 'indicatif_tel': indic})
print(f'✅ Pays: {Pays.objects.count()}')

# 3. Provinces du Burundi
burundi = Pays.objects.get(nom='Burundi')
provinces_burundi = [
    'Bubanza', 'Bujumbura Mairie', 'Bujumbura Rural', 'Bururi', 'Cankuzo',
    'Cibitoke', 'Gitega', 'Karuzi', 'Kayanza', 'Kirundo',
    'Makamba', 'Muramvya', 'Muyinga', 'Mwaro', 'Ngozi',
    'Rumonge', 'Rutana', 'Ruyigi',
]
for p in provinces_burundi:
    Province.objects.get_or_create(nom=p, pays=burundi)
print(f'✅ Provinces: {Province.objects.count()}')

# 4. Cellule exemple
Cellule.objects.get_or_create(
    code='A-000-067',
    defaults={'nom': 'Cellule 067', 'pays': Pays.objects.get(nom='Canada')}
)
print(f'✅ Cellules: {Cellule.objects.count()}')

# 5. Paramètres de l'association
parametres = [
    ('delai_approbation_jours', 'Délai d\'approbation (jours)', '60', 'INT', 'adhesion',
     'Nombre de jours maximum pour approuver une candidature d\'adhésion'),
    ('montant_frais_adhesion', 'Frais d\'adhésion (CAD)', '100.00', 'FLOAT', 'finance',
     'Montant unique des frais d\'adhésion à l\'association'),
    ('montant_cotisation_mensuelle', 'Cotisation mensuelle (CAD)', '20.00', 'FLOAT', 'finance',
     'Montant de la cotisation mensuelle obligatoire'),
    ('nombre_max_ayants_droits', 'Nombre max d\'ayants droits', '10', 'INT', 'adhesion',
     'Nombre maximum d\'ayants droits par membre'),
    ('email_notification_admin', 'Email de notification admin', 'dushigikiranecanada@gmail.com', 'STRING', 'notification',
     'Email principal pour recevoir les notifications système'),
    ('nom_association', 'Nom de l\'association', 'S.E.B.C Dushigikirane', 'STRING', 'general',
     'Nom officiel de l\'association'),
    ('devise_association', 'Devise officielle', 'Soutien Entre Burundais du Canada', 'STRING', 'general',
     'Devise officielle de l\'association'),
    ('nombre_temoins_soutien', 'Témoins requis pour soutien', '3', 'INT', 'soutien',
     'Nombre de témoins nécessaires pour une demande de soutien'),
]
for cle, libelle, valeur, type_v, cat, desc in parametres:
    ParametreAssociation.objects.get_or_create(
        cle=cle,
        defaults={'libelle': libelle, 'valeur': valeur, 'type_valeur': type_v,
                  'categorie': cat, 'description': desc}
    )
print(f'✅ Paramètres: {ParametreAssociation.objects.count()}')

# 6. Types de soutien
types_soutien = [
    ('Décès du membre', 5000.00, 'Soutien versé en cas de décès d\'un membre actif', 3),
    ('Décès du conjoint(e)', 3000.00, 'Soutien en cas de décès du conjoint d\'un membre', 3),
    ('Décès d\'un enfant', 2000.00, 'Soutien en cas de décès d\'un enfant d\'un membre', 3),
    ('Décès d\'un parent (père/mère)', 2000.00, 'Soutien en cas de décès du père ou de la mère d\'un membre', 2),
    ('Décès d\'un frère/sœur', 1000.00, 'Soutien en cas de décès d\'un frère ou d\'une sœur', 2),
]
for libelle, montant, desc, temoins in types_soutien:
    TypeSoutien.objects.get_or_create(
        libelle=libelle,
        defaults={'montant': montant, 'description': desc, 'nombre_temoins_requis': temoins}
    )
print(f'✅ Types de soutien: {TypeSoutien.objects.count()}')

# 7. Superuser admin
su, created = Membre.objects.get_or_create(
    email='evanet08@gmail.com',
    defaults={
        'nom': 'ADMIN',
        'prenom': 'Super',
        'telephone_whatsapp': '+1-000-000-0000',
        'statut': 'APPROUVE',
        'role': 'ADMIN',
        'email_verifie': True,
        'telephone_verifie': True,
        'est_superadmin': True,
        'pays_residence': Pays.objects.get(nom='Canada'),
    }
)
if created or not su.mot_de_passe_hash:
    su.set_password('123456')
    su.save()
    print('✅ Superuser créé: evanet08@gmail.com / 123456')
else:
    print('✅ Superuser existait déjà.')

# 8. Modules & Accès
modules_data = [
    # (code, nom, icone, couleur, url, ordre, visible_sidebar, requiert_approbation)
    ('dashboard',      'Dashboard',       'fas fa-chart-pie',          '#60a5fa', '/dashboard/',      1, True, False),
    ('membres',        'Mon Espace',      'fas fa-user',               '#34d399', '/membres/',        2, True, False),
    ('cotisations',    'Cotisations',      'fas fa-coins',              '#fbbf24', '/cotisations/',    3, True, True),
    ('soutien',        'Soutien',          'fas fa-hand-holding-heart', '#f472b6', '/soutien/',        4, True, True),
    ('communication',  'Communication',    'fas fa-bullhorn',           '#38bdf8', '/communication/',  5, True, False),
    ('rapports',       'Rapports',         'fas fa-file-alt',           '#a78bfa', '/rapports/',       6, True, True),
    ('administration', 'Administration',   'fas fa-cogs',               '#fb923c', '/administration/', 7, True, True),
]
for code, nom, icone, couleur, url, ordre, visible, req_appro in modules_data:
    Module.objects.get_or_create(
        code=code,
        defaults={
            'nom': nom, 'icone': icone, 'couleur': couleur, 'url': url,
            'ordre': ordre, 'visible_sidebar': visible, 'requiert_approbation': req_appro,
        }
    )
print(f'✅ Modules: {Module.objects.count()}')

# Accès par rôle —  R=lire, W=écrire, D=supprimer
ALL_ROLES = ['MEMBRE', 'CHEF_CELLULE', 'CHARGE_APPROBATION', 'CHARGE_FRAIS', 'COMPTABLE', 'ADMIN']
GESTION_ROLES = ['CHEF_CELLULE', 'CHARGE_APPROBATION', 'CHARGE_FRAIS', 'COMPTABLE', 'ADMIN']

acces_matrix = {
    'dashboard':      {'roles': GESTION_ROLES, 'rwd': (True, False, False)},
    'membres':        {'roles': ALL_ROLES,      'rwd': (True, True, False)},
    'cotisations':    {'roles': ALL_ROLES,      'rwd': (True, False, False)},
    'soutien':        {'roles': ALL_ROLES,      'rwd': (True, False, False)},
    'communication':  {'roles': ALL_ROLES,      'rwd': (True, False, False)},
    'rapports':       {'roles': GESTION_ROLES,  'rwd': (True, False, False)},
    'administration': {'roles': ['ADMIN'],      'rwd': (True, True, True)},
}

for code, conf in acces_matrix.items():
    mod = Module.objects.get(code=code)
    r, w, d = conf['rwd']
    for role in conf['roles']:
        AccesModule.objects.get_or_create(
            module=mod, role=role,
            defaults={'peut_lire': r, 'peut_ecrire': w, 'peut_supprimer': d}
        )
print(f'✅ Accès modules: {AccesModule.objects.count()}')

# 9. Types de Membres
types_membres_data = [
    # (libelle, niveau, description, peut_gerer_comm, peut_approuver, peut_gerer_finances)
    ('Gestionnaire',  'NATIONAL', 'Gestionnaire au niveau national', True, True, True),
    ('Gestionnaire',  'CELLULE',  'Gestionnaire au niveau cellule', True, True, False),
    ('Membre',        None,       'Membre régulier de l\'association', False, False, False),
]
for libelle, niveau, desc, comm, appro, fin in types_membres_data:
    lbl = f"{libelle} ({niveau})" if niveau else libelle
    TypeMembre.objects.get_or_create(
        libelle=lbl,
        defaults={
            'niveau': niveau, 'description': desc,
            'peut_gerer_communication': comm,
            'peut_approuver_membres': appro,
            'peut_gerer_finances': fin,
        }
    )
print(f'✅ Types de membres: {TypeMembre.objects.count()}')

print('\n🎉 Initialisation complète !')
