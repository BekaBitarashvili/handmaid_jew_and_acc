from django import template

from apps.core.seo import DEFAULT_LANGUAGE, OG_LOCALES, path_alternates
from apps.core.seo import json_ld as to_json_ld

register = template.Library()


@register.inclusion_tag("components/seo_head.html", takes_context=True)
def seo_head(context):
    """<head> SEO tags from the view's `seo`, with hreflang fallbacks for other pages."""
    request = context.get("request")
    seo = context.get("seo")
    alternates = (seo.alternates if seo and seo.alternates else None) or (
        path_alternates(request) if request else {}
    )
    lang = context.get("LANGUAGE_CODE", DEFAULT_LANGUAGE)
    return {
        "seo": seo,
        "alternates": alternates,
        "x_default": alternates.get(DEFAULT_LANGUAGE, ""),
        "site_settings": context.get("site_settings"),
        "og_locale": OG_LOCALES.get(lang, ""),
        "og_alternate_locales": [v for k, v in OG_LOCALES.items() if k != lang],
        "json_ld_blocks": [to_json_ld(item) for item in (seo.json_ld if seo else [])],
    }
