import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-.env")
DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "accounts",
    "marketing",
    "superadmin",
    "jobs",
    "common",
    "formbuilder",
    "navbuilder",
    "tickets",
    "pagebuilder",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "common.middleware.ActivityLogMiddleware",
]

ROOT_URLCONF = "click_to_assignment.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "common.context_processors.global_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "click_to_assignment.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "djongo",
        "NAME": os.getenv("MONGO_DB_NAME", "click_assignment"),
        "ENFORCE_SCHEMA": False,
        "CLIENT": {
            "host": os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        },
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "common:welcome"
LOGOUT_REDIRECT_URL = "accounts:login"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 30 * 60  # 30 minutes
SESSION_SAVE_EVERY_REQUEST = True  # sliding idle timeout

# Global OAuth2 / OIDC (Keycloak-ready) placeholders
GLOBAL_OIDC_ISSUER = os.getenv("GLOBAL_OIDC_ISSUER", "")
GLOBAL_OIDC_CLIENT_ID = os.getenv("GLOBAL_OIDC_CLIENT_ID", "")
GLOBAL_OIDC_CLIENT_SECRET = os.getenv("GLOBAL_OIDC_CLIENT_SECRET", "")
GLOBAL_OIDC_REDIRECT_URI = os.getenv(
    "GLOBAL_OIDC_REDIRECT_URI", "http://127.0.0.1:8000/accounts/global-sso/callback/"
)

# FX / Gem pricing
FX_API_KEY = os.getenv("FX_API_KEY", "EFIS6LQ79OC8OB10")
