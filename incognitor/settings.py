"""Django settings for the Incognitor web app.

Security posture:
- Fails fast in production when required secrets are missing.
- Hardened cookies, HSTS, CSP and other security headers out of the box.
- Argon2id password hashing.
- API rate limiting via DRF throttles.
- Sentinel agent configuration (monitoring, removal, alerting).
"""

import os
import secrets
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# `manage.py test ...` runs without production secrets; allow an ephemeral key.
TESTING = "test" in sys.argv

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG or TESTING:
        # Ephemeral key: dev/test only. Nothing is persisted across restarts.
        SECRET_KEY = "dev-insecure-" + secrets.token_urlsafe(32)
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DEBUG is False. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "core.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "incognitor.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "incognitor.wsgi.application"

# Database (SQLite by default; DB_PATH lets deployments put it on a volume)
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "db.sqlite3"))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_PATH,
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2id is the primary hasher; fall back to PBKDF2 for existing hashes.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Security headers / cookies
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Only force TLS / secure cookies when not in debug (local http dev).
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False").lower() == "true"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False  # the SPA/desktop client reads the CSRF token
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Content-Security-Policy. Built by core.middleware.SecurityHeadersMiddleware.
# Defaults keep the existing Tailwind-CDN UI working; override for production.
CSP_ENFORCE = os.getenv("CSP_ENFORCE", "False" if DEBUG else "True").lower() == "true"
CSP_DEFAULT_SRC = os.getenv("CSP_DEFAULT_SRC", "'self'")
CSP_SCRIPT_SRC = os.getenv(
    "CSP_SCRIPT_SRC", "'self' https://cdn.tailwindcss.com 'unsafe-inline'"
)
CSP_STYLE_SRC = os.getenv(
    "CSP_STYLE_SRC", "'self' 'unsafe-inline' https://fonts.googleapis.com"
)
CSP_FONT_SRC = os.getenv("CSP_FONT_SRC", "'self' https://fonts.gstatic.com")
CSP_IMG_SRC = os.getenv("CSP_IMG_SRC", "'self' data:")
CSP_CONNECT_SRC = os.getenv("CSP_CONNECT_SRC", "'self'")
CSP_REPORT_URI = os.getenv("CSP_REPORT_URI", "")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = DEBUG and os.getenv("CORS_ALLOW_ALL", "False").lower() == "true"
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
]
# Browser-extension origins are allowed to call the API using a token.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r.strip()
    for r in os.getenv(
        "CORS_ALLOWED_ORIGIN_REGEXES",
        r"^chrome-extension://.*$,^moz-extension://.*$,^safari-web-extension://.*$",
    ).split(",")
    if r.strip()
]

# ---------------------------------------------------------------------------
# Sentinel / zero-knowledge crypto
# ---------------------------------------------------------------------------
# Key used to compute blind indexes (HMAC-SHA256) of identifiers. The server
# stores only blind indexes, never plaintext PII.
BLIND_INDEX_KEY = os.getenv("BLIND_INDEX_KEY") or SECRET_KEY
# Fernet key for encrypting server-held secrets such as webhook signing keys.
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")

# Agent behaviour
SENTINEL_MONITOR_INTERVAL_HOURS = int(os.getenv("SENTINEL_MONITOR_INTERVAL_HOURS", "24"))
SENTINEL_VERIFY_INTERVAL_DAYS = int(os.getenv("SENTINEL_VERIFY_INTERVAL_DAYS", "7"))
SENTINEL_REMOVAL_DEADLINE_DAYS = int(os.getenv("SENTINEL_REMOVAL_DEADLINE_DAYS", "30"))
SENTINEL_MAX_SENDS_PER_DAY = int(os.getenv("SENTINEL_MAX_SENDS_PER_DAY", "200"))
SENTINEL_AUTO_REMOVE = os.getenv("SENTINEL_AUTO_REMOVE", "True").lower() == "true"
SENTINEL_LLM_ENABLED = os.getenv("SENTINEL_LLM_ENABLED", "False").lower() == "true"
# Domains the web-form engine may visit (SSRF allowlist). Empty = any public host.
SENTINEL_ALLOWED_WEBFORM_HOSTS = [
    h.strip()
    for h in os.getenv("SENTINEL_ALLOWED_WEBFORM_HOSTS", "").split(",")
    if h.strip()
]
# Outbound HTTP for exposure sources.
SENTINEL_HTTP_TIMEOUT = int(os.getenv("SENTINEL_HTTP_TIMEOUT", "20"))

# API keys for exposure sources (all optional; sources self-disable when empty).
HIBP_API_KEY = os.getenv("HIBP_API_KEY", "")
DEHASHED_API_KEY = os.getenv("DEHASHED_API_KEY", "")
DEHASHED_EMAIL = os.getenv("DEHASHED_EMAIL", "")
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX = os.getenv("GOOGLE_CSE_CX", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
# Optional pluggable providers.
PUBLIC_RECORDS_API_URL = os.getenv("PUBLIC_RECORDS_API_URL", "")
PUBLIC_RECORDS_API_KEY = os.getenv("PUBLIC_RECORDS_API_KEY", "")
DARKWEB_FEED_URL = os.getenv("DARKWEB_FEED_URL", "")
DARKWEB_FEED_API_KEY = os.getenv("DARKWEB_FEED_API_KEY", "")
# Search-engine de-index endpoints used by the on-device agent.
GOOGLE_DEINDEX_ENDPOINT = os.getenv("GOOGLE_DEINDEX_ENDPOINT", "")
BING_DEINDEX_ENDPOINT = os.getenv("BING_DEINDEX_ENDPOINT", "")

# Web Push (VAPID) — generate with `manage.py generate_vapid_keys`.
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_ADMIN_EMAIL = os.getenv("VAPID_ADMIN_EMAIL", "")

# Login / auth throttling
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "8"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))
REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "False").lower() == "true"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Session first so unauthenticated requests keep returning 403 (the
        # desktop client's existing contract); token auth is tried as a fallback
        # for the browser extension.
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "core.throttling.BurstUserThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("THROTTLE_ANON", "60/min"),
        "user": os.getenv("THROTTLE_USER", "1000/hour"),
        "login": os.getenv("THROTTLE_LOGIN", "10/min"),
        "signup": os.getenv("THROTTLE_SIGNUP", "5/hour"),
        "agent": os.getenv("THROTTLE_AGENT", "30/hour"),
    },
    # Pagination is intentionally not enabled globally: the existing desktop
    # client expects plain lists from /api/brokers/ and /api/scans/.
}

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# Email (for sending deletion requests)
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "privacy@incognitor.app")

# Playwright
PLAYWRIGHT_BROWSERS_PATH = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "")
# Only enable inside a locked-down container running as non-root; never on a
# host that runs untrusted browser content alongside other workloads.
PLAYWRIGHT_NO_SANDBOX = os.getenv("PLAYWRIGHT_NO_SANDBOX", "False").lower() == "true"

# Logging: structured-ish, sent to stdout; audit events live in the DB.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
