"""
Django settings for infoseminario project.
"""

import os
import json
from pathlib import Path
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-*i50%m07#_0twx*%65ha%&sg*tje1!69xihb7y)#-aeb+^z$5k'

DEBUG = True

ALLOWED_HOSTS = ['.vercel.app', 'localhost', '127.0.0.1']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'appseminario',  # Tu aplicación principal
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # WhiteNoise para servir CSS/JS en Vercel
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'infoseminario.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',  # Habilita {{ MEDIA_URL }} en templates
            ],
        },
    },
]

WSGI_APPLICATION = 'infoseminario.wsgi.application'


# Database
# Usa DATABASE_URL (Postgres) si existe; si no, SQLite local para desarrollo
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization (Configurado a Español)
LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True


# Static & Media files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Almacenamiento optimizado y comprimido para WhiteNoise
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Firebase Admin SDK Configuration
import firebase_admin
from firebase_admin import credentials

FIREBASE_KEY_PATH = BASE_DIR / 'firebase-key.json'

if not firebase_admin._apps:
    if FIREBASE_KEY_PATH.exists():
        # Uso Local
        cred = credentials.Certificate(str(FIREBASE_KEY_PATH))
        firebase_admin.initialize_app(cred)
    elif os.environ.get('FIREBASE_CREDENTIALS_JSON'):
        # Uso en Vercel (con limpieza de comillas y caracteres extra)
        raw_json = os.environ.get('FIREBASE_CREDENTIALS_JSON', '').strip()
        if (raw_json.startswith('"') and raw_json.endswith('"')) or (raw_json.startswith("'") and raw_json.endswith("'")):
            raw_json = raw_json[1:-1]
        
        cred_dict = json.loads(raw_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)


# Guardar la sesión directamente en cookies para no depender de la BD SQLite
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

# Asegurar compatibilidad de cookies en Vercel
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'