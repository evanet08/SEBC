# SEBC 🎓

**SEBC** est une application Django faisant partie de l'écosystème éducatif eSchool/MonEcole, déployée sur le même serveur que les projets eSchoolStructure et MonEcole.

## 🚀 Fonctionnalités

_Projet en cours de développement._

## 🛠️ Stack Technique

- **Framework** : Django 6.0
- **Base de Données** : MySQL / MariaDB (via `sebc_dbase`)
- **Serveur WSGI** : Gunicorn
- **Frontend** : Vanilla JS, CSS3 (Glassmorphism), FontAwesome 6, Google Fonts (Inter)
- **Connecteur MySQL** : PyMySQL avec patch de compatibilité Django 6

## 📦 Installation et Configuration Locale

### 1. Clonage et Environnement
```bash
git clone https://github.com/evanet08/SEBC.git
cd SEBC
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration (`.env`)
Créez un fichier `.env` à la racine :
```env
SECRET_KEY="votre_cle_secrete"
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_ENGINE=django.db.backends.mysql
DB_NAME=sebc_dbase
DB_USER=votre_user
DB_PASSWORD=votre_password
DB_HOST=localhost
DB_PORT=3306
```

### 3. Lancer le serveur (développement)
```bash
mkdir -p tmp
python manage.py migrate
python manage.py runserver
```

### 4. Lancer avec Gunicorn (production)
```bash
gunicorn -c gunicorn.conf.py SEBC.wsgi:application
```

## 🌐 Déploiement (Production)

### Particularités Django 6 x MySQL
Même patch `pymysql` que eSchoolStructure dans `SEBC/__init__.py`.

### Gunicorn
- **Config** : `gunicorn.conf.py`
- **Commande** : `gunicorn -c gunicorn.conf.py SEBC.wsgi:application`
- **Variables d'environnement** :
  - `GUNICORN_BIND` : adresse de bind (défaut `0.0.0.0:8000`)
  - `GUNICORN_WORKERS` : nombre de workers (défaut `CPU * 2 + 1`)
  - `GUNICORN_RELOAD` : `true` pour le hot-reload en dev

### Repository Git
```
https://github.com/evanet08/SEBC.git
```

## 📂 Structure du Projet
```
SEBC/
├── SEBC/              # Configuration globale Django
│   ├── __init__.py    # Patch PyMySQL
│   ├── settings.py    # Paramètres projet
│   ├── urls.py        # URLs racine
│   ├── wsgi.py        # WSGI standard
│   └── asgi.py        # ASGI standard
├── sebc_app/          # Application principale
│   ├── models.py      # Modèles de données
│   ├── views.py       # Vues
│   ├── urls.py        # Routes de l'app
│   ├── templates/     # Templates HTML
│   ├── static/        # CSS, JS, images
│   └── migrations/    # Migrations Django
├── manage.py          # CLI Django
├── gunicorn.conf.py   # Configuration Gunicorn
├── requirements.txt   # Dépendances Python
├── .env               # Variables d'environnement
└── .gitignore         # Fichiers ignorés par Git
```

---
© 2026 — **SEBC** — ICT Group Entreprise
