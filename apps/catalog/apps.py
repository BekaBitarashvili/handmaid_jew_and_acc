from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatalogConfig(AppConfig):
    name = "apps.catalog"
    verbose_name = _("Catalog")

    def ready(self) -> None:
        from . import signals  # noqa: F401
        from .images import install_avif_compat

        install_avif_compat()
