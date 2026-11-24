from django.http import HttpRequest
from django.utils.functional import SimpleLazyObject

from .models import SiteSettings


def site_settings(request: HttpRequest) -> dict:
    """Expose SiteSettings as `site_settings`; queried only if a template uses it."""
    return {"site_settings": SimpleLazyObject(SiteSettings.load)}
