"""Local development settings."""

from .base import *  # noqa: F403
from .base import INSTALLED_APPS, MIDDLEWARE, env

DEBUG = True
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-secret-key-do-not-use-in-production")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])

# Run huey tasks synchronously in-process, so no worker or Redis is needed in dev.
HUEY = {"immediate": True, "name": "shop"}

# --- Debug toolbar ----------------------------------------------------------
INSTALLED_APPS = [*INSTALLED_APPS, "debug_toolbar"]
MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware", *MIDDLEWARE]
INTERNAL_IPS = ["127.0.0.1"]
