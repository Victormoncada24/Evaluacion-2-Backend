"""
Configuración del proyecto EVA-2 · Proyecto 3: Venta de Entradas.

Bloques principales (útiles para la defensa oral):
  1. Apps instaladas  -> NO incluye django.contrib.admin (requisito: sin admin de Django).
  2. Base de datos    -> PostgreSQL con django.db.backends.postgresql.
  3. DRF + JWT        -> autenticación SOLO por token, respuestas SOLO JSON.
  4. SimpleJWT        -> access/refresh, rotación y lista negra (logout real).
  5. Swagger          -> drf-spectacular (el acceso se restringe en config/urls.py).
  6. Reglas de negocio-> máximo de tickets por compra y minutos de reserva.
  7. Datos del alumno -> se muestran en el footer de las vistas HTML.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')  # lee las variables del archivo .env si existe

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'clave-solo-para-desarrollo')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# --------------------------------------------------------------------------
# 1. APPS INSTALADAS
# 'django.contrib.admin' se omite a propósito: así no existe /admin/ ni nada
# del panel de Django. Los superusuarios se crean con `createsuperuser`.
# --------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Terceros
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',  # permite invalidar refresh tokens (logout)
    'django_filters',
    'drf_spectacular',
    # Apps del proyecto
    'accounts',
    'catalogo',
    'ventas',
    'panel',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'panel.context_processors.datos_alumno',  # inyecta {{ ALUMNO }} al footer
    ]},
}]

# --------------------------------------------------------------------------
# 2. BASE DE DATOS: PostgreSQL
# --------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'boletaje'),
        'USER': os.environ.get('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Usuario propio con campo `rol` (Espectador / Organizador)
AUTH_USER_MODEL = 'accounts.Usuario'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Login por sesión SOLO para las vistas HTML (dashboard y Swagger del administrador)
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# --------------------------------------------------------------------------
# 3. DJANGO REST FRAMEWORK
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    # La API se autentica únicamente con JWT (cabecera Authorization: Bearer <token>)
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # "Seguro por defecto": todo exige login salvo que la vista indique otra cosa
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    # Solo JSON: así tampoco aparece la API navegable de DRF
    'DEFAULT_RENDERER_CLASSES': ('rest_framework.renderers.JSONRenderer',),
    # Filtros globales: django-filter + búsqueda + ordenamiento
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# --------------------------------------------------------------------------
# 4. JWT (SimpleJWT)
# --------------------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),   # token corto para operar
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),      # token largo para renovar
    'ROTATE_REFRESH_TOKENS': True,                    # cada refresh entrega uno nuevo
    'BLACKLIST_AFTER_ROTATION': True,                 # y el anterior queda invalidado
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# --------------------------------------------------------------------------
# 5. OPENAPI / SWAGGER
# --------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'API de Venta de Entradas (EVA-2 · Proyecto 3)',
    'DESCRIPTION': 'Boletaje para eventos y conciertos. Autenticación JWT con roles '
                   'Espectador y Organizador. Usa el botón "Authorize" con: Bearer <access>.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SERVE_PERMISSIONS': ['rest_framework.permissions.IsAdminUser'],
}

# --------------------------------------------------------------------------
# 6. REGLAS DE NEGOCIO
# --------------------------------------------------------------------------
MAX_TICKETS_POR_COMPRA = 5   # máximo de tickets por usuario en cada compra
MINUTOS_RESERVA = 10         # tiempo que se retienen los tickets seleccionados

# --------------------------------------------------------------------------
# 7. DATOS DEL ALUMNO (footer)
# --------------------------------------------------------------------------
ALUMNO = {
    'nombre': os.environ.get('ALUMNO_NOMBRE', 'Nombre Apellido'),
    'seccion': os.environ.get('ALUMNO_SECCION', '001'),
    'anio': os.environ.get('ALUMNO_ANIO', '2026'),
}
