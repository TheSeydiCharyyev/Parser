import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "api.apps.ApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "parser"),
        "USER": os.environ.get("POSTGRES_USER", "parser"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "parser"),
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": int(os.environ.get("POSTGRES_PORT", "5432")),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Parser API",
    "VERSION": "1.0.0",
}

# Internal service-to-service auth (worker/bot/scheduler)
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "")

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
REDIS_STREAM_CHECKS = os.environ.get("REDIS_STREAM_CHECKS", "stream:checks")
REDIS_STREAM_NOTIFY = os.environ.get("REDIS_STREAM_NOTIFY", "stream:notify")
REDIS_GROUP_CHECKS = os.environ.get("REDIS_GROUP_CHECKS", "workers")
REDIS_GROUP_NOTIFY = os.environ.get("REDIS_GROUP_NOTIFY", "bot")
_notify_maxlen_raw = os.environ.get("REDIS_STREAM_MAXLEN_NOTIFY", "").strip()
REDIS_STREAM_MAXLEN_NOTIFY = int(_notify_maxlen_raw) if _notify_maxlen_raw else 0

_checks_maxlen_raw = os.environ.get("REDIS_STREAM_MAXLEN_CHECKS", "").strip()
REDIS_STREAM_MAXLEN_CHECKS = int(_checks_maxlen_raw) if _checks_maxlen_raw else 0
