"""Settings shared by every environment. Environment-specific files import from here."""

from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
if (BASE_DIR / ".env").exists():
    environ.Env.read_env(BASE_DIR / ".env")

# SECRET_KEY, DEBUG and ALLOWED_HOSTS are set per environment.
DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS: list[str] = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# The admin lives at a non-guessable path (SPEC §10).
ADMIN_URL: str = env("ADMIN_URL", default="manage/").strip("/") + "/"

# --- Applications -----------------------------------------------------------

INSTALLED_APPS = [
    # Must come before django.contrib.admin.
    "unfold",
    "unfold.contrib.forms",  # WYSIWYG editor for rich-text fields
    "modeltranslation",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",  # built-in widget templates for FORM_RENDERER below
    # Third party
    "django_htmx",
    "huey.contrib.djhuey",
    "easy_thumbnails",
    # Local
    "apps.core",
    "apps.catalog",
    "apps.cart",
    "apps.orders",
    "apps.payments",
    "apps.promotions",
    "apps.wishlist",
    "apps.pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.core.middleware.LocaleMiddleware",  # ignores Accept-Language
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

# Render form widgets with TEMPLATES (incl. templates/), so the project can
# override widget templates such as unfold's rich-text toolbar.
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_settings",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://shop:shop@127.0.0.1:5432/shop"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth -------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalization (SPEC §3) -----------------------------------------

LANGUAGE_CODE = "ka"
LANGUAGES = [
    ("ka", _("Georgian")),
    ("en", _("English")),
]
LOCALE_PATHS = [
    BASE_DIR / "locale",  # ours (makemessages writes here)
    BASE_DIR / "locale_vendor",  # Georgian for unfold / Django admin UI strings
]
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
TIME_ZONE = "Asia/Tbilisi"
USE_I18N = True
USE_TZ = True

MODELTRANSLATION_DEFAULT_LANGUAGE = "ka"
MODELTRANSLATION_LANGUAGES = ("ka", "en")
MODELTRANSLATION_FALLBACK_LANGUAGES = ("ka",)

# --- Static & media ---------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Generated thumbnails live next to the originals (S3 in prod, see prod.py).
    "easy_thumbnails": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --- Product images (SPEC §5): 4:5 crops at 400/800/1200/1800px, AVIF + WebP ---
# Formats are chosen per call in apps/catalog/images.py; this is only the fallback.
THUMBNAIL_EXTENSION = "webp"
THUMBNAIL_QUALITY = 80
THUMBNAIL_PRESERVE_EXTENSIONS = None
THUMBNAIL_TRANSPARENCY_EXTENSION = "webp"
THUMBNAIL_SUBDIR = "thumbs"

# --- Email ------------------------------------------------------------------

vars().update(env.email_url("EMAIL_URL", default="consolemail://"))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="shop@example.com")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- Cache -------------------------------------------------------------------
# Per-process memory cache by default; production uses Redis (prod.py).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- Background jobs (huey) -------------------------------------------------

REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
HUEY = {
    "huey_class": "huey.RedisHuey",
    "name": "shop",
    "immediate": False,
    "connection": {"url": REDIS_URL},
    "consumer": {"workers": 2, "worker_type": "thread"},
}

# --- Security defaults (hardened further in prod.py) ------------------------

X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
# HTMX gets the token from `hx-headers` rendered into <body>, so JS never reads the cookie.
CSRF_COOKIE_HTTPONLY = True

# --- Logging ----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name}: {message}", "style": "{"},
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# --- Admin (django-unfold), SPEC §10 ----------------------------------------
# UI language follows the language cookie and defaults to Georgian; the header
# switcher (SHOW_LANGUAGES) flips it to English via /i18n/setlang/.


def _static(path: str) -> str:
    from django.templatetags.static import static

    return static(path)


def _admin_url(name: str):
    from django.urls import reverse_lazy

    return reverse_lazy(name)


UNFOLD = {
    "SITE_TITLE": "apps.core.admin_config.site_title",
    "SITE_HEADER": "apps.core.admin_config.site_title",
    "SITE_SUBHEADER": _("Shop admin"),
    "SITE_SYMBOL": "diamond",
    "SITE_URL": "/",
    "SITE_FAVICONS": [
        {"rel": "icon", "type": "image/svg+xml", "href": "/static/brand/favicon.svg"},
    ],
    "SHOW_LANGUAGES": True,
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "BORDER_RADIUS": "2px",
    # Georgian in FiraGO + phone layout fix (static/css/admin.css).
    "STYLES": [lambda request: _static("css/admin.css")],
    # Brand palette (assets/css/main.css tokens converted to OKLCH).
    "COLORS": {
        "base": {
            "50": "oklch(97.4% .010 81.8)",  # ivory
            "100": "oklch(94.2% .018 81.3)",  # cream
            "200": "oklch(87.9% .031 76.9)",  # sand
            "300": "oklch(80% .036 74)",
            "400": "oklch(67.3% .043 69.4)",  # taupe
            "500": "oklch(52.4% .042 69.4)",  # taupe-text
            "600": "oklch(40.1% .042 54.9)",  # cocoa
            "700": "oklch(33% .035 52)",
            "800": "oklch(26.1% .024 49.6)",  # espresso
            "900": "oklch(21% .020 49)",
            "950": "oklch(14% .015 49)",
        },
        "primary": {
            "50": "oklch(97% .015 77)",
            "100": "oklch(94% .030 77)",
            "200": "oklch(88% .050 77)",
            "300": "oklch(80% .070 77)",
            "400": "oklch(66.4% .083 77.4)",  # gold
            "500": "oklch(58% .078 77)",
            "600": "oklch(52.4% .067 76.9)",  # gold-text
            "700": "oklch(45% .058 76)",
            "800": "oklch(38% .048 75)",
            "900": "oklch(31% .038 74)",
            "950": "oklch(22% .028 72)",
        },
    },
    "SIDEBAR": {
        "show_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Catalog"),
                "items": [
                    {
                        "title": _("Products"),
                        "icon": "diamond",
                        "link": _admin_url("admin:catalog_product_changelist"),
                    },
                    {
                        "title": _("Categories"),
                        "icon": "category",
                        "link": _admin_url("admin:catalog_category_changelist"),
                    },
                    {
                        "title": _("Stones"),
                        "icon": "texture",
                        "link": _admin_url("admin:catalog_stone_changelist"),
                    },
                    {
                        "title": _("Materials"),
                        "icon": "layers",
                        "link": _admin_url("admin:catalog_material_changelist"),
                    },
                    {
                        "title": _("Sales"),
                        "icon": "sell",
                        "link": _admin_url("admin:promotions_sale_changelist"),
                    },
                ],
            },
            {
                "title": _("Orders"),
                "items": [
                    {
                        "title": _("Delivery options"),
                        "icon": "local_shipping",
                        "link": _admin_url("admin:orders_deliveryoption_changelist"),
                    },
                ],
            },
            {
                "title": _("Settings"),
                "items": [
                    {
                        "title": _("Site settings"),
                        "icon": "tune",
                        "link": _admin_url("admin:core_sitesettings_changelist"),
                    },
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": _admin_url("admin:auth_user_changelist"),
                    },
                ],
            },
        ],
    },
}
