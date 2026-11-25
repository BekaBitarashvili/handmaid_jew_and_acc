"""Settings for the pytest suite."""

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
HUEY = {"immediate": True, "name": "shop-test"}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
# Don't require a collectstatic run (STATIC_ROOT) before tests.
WHITENOISE_AUTOREFRESH = True
