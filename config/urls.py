from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.views import apple_touch_icon, favicon_ico, healthz

# Language-neutral URLs.
urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("favicon.ico", favicon_ico),
    path("apple-touch-icon.png", apple_touch_icon),
    path("i18n/", include("django.conf.urls.i18n")),  # POST /i18n/setlang/
    path(settings.ADMIN_URL, admin.site.urls),
]

# Public site: /ka/... and /en/... (SPEC §3: default language is prefixed too).
urlpatterns += i18n_patterns(
    path("", include("apps.core.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.pages.urls")),
    path("", include("apps.cart.urls")),
    path("", include("apps.wishlist.urls")),
    prefix_default_language=True,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if "debug_toolbar" in settings.INSTALLED_APPS:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
