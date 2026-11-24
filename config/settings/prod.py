"""Production settings. Every secret is required; a missing one fails at startup."""

import sentry_sdk

from .base import *  # noqa: F403
from .base import LOGGING, REDIS_URL, env

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# --- HTTPS (TLS terminates at Caddy/Nginx) ----------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]  # container healthchecks use plain HTTP
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Start low; raise to 31536000 (1 year) once HTTPS is confirmed working on the domain.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# --- Storage: S3-compatible media, WhiteNoise static ------------------------
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": env("AWS_ACCESS_KEY_ID"),
            "secret_key": env("AWS_SECRET_ACCESS_KEY"),
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
            "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=None),
            "region_name": env("AWS_S3_REGION_NAME", default=None),
            "custom_domain": env("AWS_S3_CUSTOM_DOMAIN", default=None),
            "file_overwrite": False,
            # Product images are public. Private uploads (commission references,
            # Phase 2) will get their own storage with signed URLs.
            "querystring_auth": False,
        },
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- Background jobs --------------------------------------------------------
HUEY = {
    "huey_class": "huey.RedisHuey",
    "name": "shop",
    "immediate": False,
    "connection": {"url": env("REDIS_URL", default=REDIS_URL)},
    "consumer": {"workers": 2, "worker_type": "thread"},
}

# --- Logging: structured JSON to stdout -------------------------------------
LOGGING["handlers"]["console"]["formatter"] = "json"

# --- Sentry -----------------------------------------------------------------
if SENTRY_DSN := env("SENTRY_DSN", default=""):
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
        send_default_pii=False,
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
    )
