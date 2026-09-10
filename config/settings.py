"""Django settings for the meeting scheduler.

Configuration is read from environment variables (or a local `.env` file - see
`.env.example`). Only SECRET_KEY is required in production.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")  # no-op if the file is absent

# --- Core -----------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key-change-me")
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "scheduling",
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
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database -----------------------------------------------------------

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

# --- Auth --------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Where the staff pages send an unauthenticated visitor, and back again.
LOGIN_URL = "scheduling:staff-login"
LOGIN_REDIRECT_URL = "scheduling:staff-home"
LOGOUT_REDIRECT_URL = "scheduling:staff-login"

# --- i18n / time ------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # datetimes are stored in UTC; USE_TZ keeps them aware
USE_I18N = True
USE_TZ = True

# --- Static files ----------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email ---------------------------------------------------------
# With no EMAIL_HOST set, messages are printed to the console.

DEFAULT_FROM_EMAIL = env("EMAIL_FROM", default="scheduler@example.com")

if env("EMAIL_HOST", default=""):
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": env("EMAIL_HOST"),
                "port": env.int("EMAIL_PORT", default=587),
                "username": env("EMAIL_HOST_USER", default=""),
                "password": env("EMAIL_HOST_PASSWORD", default=""),
                "use_tls": env.bool("EMAIL_USE_TLS", default=True),
            },
        },
    }
else:
    MAILERS = {
        "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"},
    }

# --- Booking rules -------------------------------------------------
# Business hours below are expressed in SCHEDULER["TIMEZONE"].

SCHEDULER = {
    "HOST_NAME": env("HOST_NAME", default="Our Team"),
    "BASE_URL": env("BASE_URL", default="http://localhost:8000"),
    "TIMEZONE": env("SCHEDULER_TIMEZONE", default="UTC"),
    "BUSINESS_START_HOUR": env.int("BUSINESS_START_HOUR", default=9),
    "BUSINESS_END_HOUR": env.int("BUSINESS_END_HOUR", default=17),
    "SLOT_MINUTES": env.int("SLOT_MINUTES", default=30),
    # Longest booking a client may make, counted in back-to-back slots.
    # 2 with 30-minute slots => they can book 30 or 60 minutes.
    "MAX_CONSECUTIVE_SLOTS": env.int("MAX_CONSECUTIVE_SLOTS", default=2),
    "AVAILABLE_WEEKDAYS": [
        int(d) for d in env.list("AVAILABLE_WEEKDAYS", default=["0", "1", "2", "3", "4"])
    ],
    "BOOKING_HORIZON_DAYS": env.int("BOOKING_HORIZON_DAYS", default=14),
    "MIN_NOTICE_HOURS": env.int("MIN_NOTICE_HOURS", default=2),
}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # The booking API is public by design (clients have no accounts); the
    # unguessable manage_token is what protects an individual booking.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}
