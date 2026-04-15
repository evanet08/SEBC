from pathlib import Path
from decouple import Config, RepositoryEnv
import os
import pymysql

# Patch MySQL
pymysql.install_as_MySQLdb()
import MySQLdb
# Monkey-patch version to satisfy Django's check
if MySQLdb.version_info < (2, 2, 1):
    MySQLdb.version_info = (2, 2, 1, 'final', 0)

BASE_DIR = Path(__file__).resolve().parent.parent

env_path = BASE_DIR / '.env'

if env_path.exists():
    env_config = Config(RepositoryEnv(env_path))
else:
    from decouple import config as env_config

SECRET_KEY = env_config('SECRET_KEY', default='django-insecure-sebc-dev-key-change-me')

DEBUG = env_config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = env_config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

CSRF_TRUSTED_ORIGINS = env_config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://localhost'
).split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'sebc_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'SEBC.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'sebc_app.context_processors.sidebar_modules',
            ],
        },
    },
]

WSGI_APPLICATION = 'SEBC.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': env_config('DB_ENGINE', default='django.db.backends.sqlite3'),
        'NAME': env_config('DB_NAME', default=str(BASE_DIR / 'db.sqlite3')),
        'USER': env_config('DB_USER', default=''),
        'PASSWORD': env_config('DB_PASSWORD', default=''),
        'HOST': env_config('DB_HOST', default=''),
        'PORT': env_config('DB_PORT', default=''),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# =============================================================
# SESSION SECURITY — 30-minute inactivity timeout
# =============================================================
SESSION_COOKIE_AGE = 1800           # Cookie expires 30 minutes after last modification
SESSION_SAVE_EVERY_REQUEST = True   # Reset the cookie on every request (activity = extend)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Also die when the browser closes

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Allow same-origin iframes (for document viewer modals)
X_FRAME_OPTIONS = 'SAMEORIGIN'

# =============================================================
# BREVO EMAIL API
# =============================================================
BREVO_API_KEY = env_config('BREVO_API_KEY', default='')
DEFAULT_FROM_EMAIL = env_config('DEFAULT_FROM_EMAIL', default='dushigikiranecanada@gmail.com')
DEFAULT_FROM_NAME = env_config('DEFAULT_FROM_NAME', default='SEBC Dushigikirane')

# Logging to file for debug on server
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'tmp', 'django_debug.log'),
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'DEBUG',
    },
}
