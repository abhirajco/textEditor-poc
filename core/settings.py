import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# ==============================================================================
# PATH CONFIGURATION
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# Add 'apps' folder to sys.path so all apps are importable directly
APPS_DIR = os.path.join(BASE_DIR, 'apps')
if APPS_DIR not in sys.path:
    sys.path.insert(0, APPS_DIR)

env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

if os.getenv('DB_PASSWORD'):
    print("✅ .env detected and loaded.")
else:
    print("⚠️  .env NOT found or DB_PASSWORD missing.")

# ==============================================================================
# SECURITY & CORE
# ==============================================================================
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key-change-me')
DEBUG      = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']

AUTH_USER_MODEL = 'accounts.User'

# ==============================================================================
# INSTALLED APPS
# ==============================================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'cloudinary_storage',
    'django.contrib.staticfiles',

    # Third Party
    'rest_framework',
    'drf_spectacular',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'cloudinary',

    # Internal Apps
    'accounts',
    'content',
    'board',
    'utils',
]

# ==============================================================================
# MIDDLEWARE
# ==============================================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF    = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

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
            ],
        },
    },
]

# ==============================================================================
# DATABASE
# ==============================================================================
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     os.getenv('DB_NAME'),
        'USER':     os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST':     os.getenv('DB_HOST', 'localhost'),
        'PORT':     os.getenv('DB_PORT', '5432'),
    }
}

# ==============================================================================
# REDIS CACHE
# ==============================================================================
CACHES = {
    "default": {
        "BACKEND":  "django_redis.cache.RedisCache",
        "LOCATION": os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

# ==============================================================================
# JWT & REST FRAMEWORK
# ==============================================================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',  # ← add inside existing dict
}



SPECTACULAR_SETTINGS = {
    'TITLE':       'Merged Platform API',
    'DESCRIPTION': (
        'Backend API for InSight (content management + approval workflow) '
        'and Kanban Board. Built with Django REST Framework, PostgreSQL, Redis, and Docker.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,

    # Group endpoints by app
    'TAGS': [
        {'name': 'Auth',     'description': 'Signup, OTP verify, login, logout, token refresh'},
        {'name': 'Users',    'description': 'User management and RBAC (admin only)'},
        {'name': 'Content',  'description': 'InSight — articles, versions, approval workflow'},
        {'name': 'Board',    'description': 'Kanban board — tasks, transfer, discussion, filters'},
    ],

    'SECURITY': [{'BearerAuth': []}],
    'COMPONENTS': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
}

SIMPLE_JWT = {
    "USER_ID_FIELD": "user_id",
    "USER_ID_CLAIM": "user_id",
    "ACCESS_TOKEN_LIFETIME":  timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS":  True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN":      True,
    "ALGORITHM":              "HS256",
    "AUTH_HEADER_TYPES":      ("Bearer",),
}

# ==============================================================================
# EMAIL  (Outlook / Office 365)
# ==============================================================================
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = 'smtp.office365.com'
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = os.getenv('O_EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('O_EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL  = f'InSight + Kanban <{os.getenv("O_EMAIL_HOST_USER")}>'

# Uncomment below to print emails to terminal instead of sending (dev mode):
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ==============================================================================
# CLOUDINARY  (for article image uploads)
# ==============================================================================
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY':    os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# ==============================================================================
# CORS
# ==============================================================================
CORS_ALLOW_ALL_ORIGINS = True   # Tighten this in production

# ==============================================================================
# AUTH VALIDATORS / I18N / STATIC
# ==============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ==============================================================================
# CELERY CONFIGURATION
# ==============================================================================
CELERY_BROKER_URL        = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND    = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT    = ["json"]
CELERY_TASK_SERIALIZER   = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE          = "UTC"
CELERY_TASK_TRACK_STARTED = True
