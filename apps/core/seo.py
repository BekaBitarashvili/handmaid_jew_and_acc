"""Per-page SEO data (SPEC §12): title, description, canonical, hreflang, robots,
Open Graph and JSON-LD. Views build a `Seo`; templates/components/seo_head.html renders it."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from django.http import HttpRequest
from django.urls import translate_url
from django.utils import translation
from django.utils.html import strip_tags
from django.utils.safestring import SafeString, mark_safe
from django.utils.text import Truncator

LANGUAGES = ("ka", "en")
DEFAULT_LANGUAGE = "ka"  # x-default (SPEC §3)
OG_LOCALES = {"ka": "ka_GE", "en": "en_US"}


@dataclass
class Seo:
    title: str
    description: str = ""
    canonical: str = ""
    alternates: dict[str, str] = field(default_factory=dict)  # language -> absolute URL
    noindex: bool = False
    og_type: str = "website"
    og_image: str = ""
    json_ld: list[dict] = field(default_factory=list)


def describe(*candidates: str, length: int = 155) -> str:
    """First non-empty candidate as plain text, cut at a word boundary."""
    for text in candidates:
        plain = " ".join(strip_tags(text or "").split())
        if plain:
            return Truncator(plain).chars(length)
    return ""


def alternates(request: HttpRequest, url_for: Callable[[], str]) -> dict[str, str]:
    """Absolute URL of the same page in every language (`url_for` runs per language)."""
    result = {}
    for lang in LANGUAGES:
        with translation.override(lang):
            result[lang] = request.build_absolute_uri(url_for())
    return result


def path_alternates(request: HttpRequest) -> dict[str, str]:
    """Fallback for pages without their own Seo: re-resolve the current path per language."""
    return {
        lang: request.build_absolute_uri(translate_url(request.path, lang)) for lang in LANGUAGES
    }


def json_ld(data: dict) -> SafeString:
    """JSON for <script type="application/ld+json">, safe against "</script>" in content."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for char, escape in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        text = text.replace(char, escape)
    return mark_safe(text)  # noqa: S308 (escaped above)


def breadcrumbs(request: HttpRequest, items: list[tuple[str, str]]) -> dict:
    """schema.org BreadcrumbList from (name, path) pairs."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": request.build_absolute_uri(path),
            }
            for position, (name, path) in enumerate(items, start=1)
        ],
    }
