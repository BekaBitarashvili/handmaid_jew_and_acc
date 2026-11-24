"""Callbacks referenced from settings.UNFOLD (kept out of settings to avoid model imports)."""

from django.http import HttpRequest


def site_title(request: HttpRequest) -> str:
    from .models import SiteSettings

    return SiteSettings.load().brand_name
