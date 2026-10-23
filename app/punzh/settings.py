"""
Django settings for punzh project.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.2/ref/settings/
"""

import os
from pathlib import Path

import environ

from punzh.dotenv import DOTENV_PATH, dotenv_should_overwrite

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
# Compose bind-mounts the host .env over DOTENV_PATH, so a container restart
# sees edits without an image rebuild. The runserver worker inherits
# os.environ from the reloader parent, so overwrite there. Elsewhere,
# including uwsgi after restart, existing variables win.
env.read_env(DOTENV_PATH, overwrite=dotenv_should_overwrite())


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", True)

ALLOWED_HOSTS = ["punzhina.krc.karelia.ru", "punzh.local", "localhost", "127.0.0.1"]

# Required since Django 4.0 for HTTPS POSTs (admin, forms) behind TLS.
CSRF_TRUSTED_ORIGINS = [
    "https://punzhina.krc.karelia.ru",
    "https://punzh.local",
    "http://punzh.local",
    "http://localhost",
    "http://127.0.0.1",
]

# Keep AutoField so existing integer PKs do not get BigAutoField migrations.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# --- AI-поиск (рантайм): классификация запроса через шлюз Timeweb ---
# Дефолты заданы, чтобы отсутствие ключа НЕ роняло приложение: при пустом ключе
# или недоступности шлюза AI-поиск тихо откатывается на лексический поиск.
TIMEWEB_AI_API_KEY = env("TIMEWEB_AI_API_KEY", default="")
TIMEWEB_AI_BASE_URL = env("TIMEWEB_AI_BASE_URL", default="https://api.timeweb.ai/v1")
# Разбор запроса поиска — YandexGPT (русский). Классификация нового слова —
# DeepSeek (консистентно с пакетной разметкой 16k).
TIMEWEB_AI_MODEL_QUERY = env("TIMEWEB_AI_MODEL_QUERY", default="yandex/yandexgpt-lite")
TIMEWEB_AI_MODEL_CLASSIFY = env(
    "TIMEWEB_AI_MODEL_CLASSIFY", default="deepseek/deepseek-v4-flash"
)
# Soft re-rank of AI search tops (same gateway; default = query model).
TIMEWEB_AI_MODEL_RERANK = env("TIMEWEB_AI_MODEL_RERANK", default=TIMEWEB_AI_MODEL_QUERY)
# Second LLM pass after SQL. On in DEBUG; set AI_SEARCH_LLM_RERANK=0 to disable.
AI_SEARCH_LLM_RERANK = env.bool("AI_SEARCH_LLM_RERANK", default=DEBUG)

# Application definition
INSTALLED_APPS = [
    "bootstrap4",
    "dict.apps.DictConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_static_fontawesome",
    "django.contrib.postgres",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "dict.middleware.OntologyClassifyNoticeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

handler404 = "dict.views.page_not_found"

ROOT_URLCONF = "punzh.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "punzh.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "punzh_dict",
        "USER": env("PG_USER"),
        "PASSWORD": env("PG_PASS"),
        "HOST": "punzh_db",
        "PORT": 5432,
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "ru"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "/static/"

STATICFILES_DIRS = (os.path.join(BASE_DIR, "static"),)

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media/")
