"""
Script d'initialisation des données de base SEBC.
Lancer avec: python manage.py shell < init_data.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SEBC.settings')
django.setup()

from sebc_app.models import TypeAyantDroit, Pays, Cellule, Membre

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

# 3. Cellule exemple
Cellule.objects.get_or_create(
    code='A-000-067',
    defaults={'nom': 'Cellule 067', 'pays': Pays.objects.get(nom='Canada')}
)
print(f'✅ Cellules: {Cellule.objects.count()}')

# 4. Superuser admin
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

print('\n🎉 Initialisation terminée !')
