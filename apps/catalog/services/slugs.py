"""Translated URL slugs: `ka` transliterated to Latin, `en` from the English name (SPEC §3)."""

from django.db import models
from django.utils.text import slugify

from apps.core.transliteration import slugify_ka

LANGUAGES = ("ka", "en")


def unique_slug(model: type[models.Model], field: str, base: str, exclude_pk=None) -> str:
    """`base`, or `base-2`, `base-3`… — whatever is free in `field`."""
    from apps.catalog.models import RESERVED_CATEGORY_SLUGS, Category

    base = base or "item"
    if model is Category and base in RESERVED_CATEGORY_SLUGS:
        base = f"{base}-items"
    max_length = model._meta.get_field(field).max_length
    base = base[: max_length - 4].strip("-")
    queryset = model._default_manager.all()
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    candidate, n = base, 2
    while queryset.filter(**{field: candidate}).exists():
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def fill_translated_slugs(instance: models.Model, source: str = "name") -> None:
    """Fill empty `slug_ka` / `slug_en`; normalise and de-duplicate typed ones.

    slug_ka: Georgian name transliterated ("ქარვის ყელსაბამი" -> "karvis-yelsabami").
    slug_en: English name, or the Georgian slug when there is no English name yet.
    """
    model = type(instance)
    ka_name = getattr(instance, f"{source}_ka") or ""
    en_name = getattr(instance, f"{source}_en") or ""

    ka_value = instance.slug_ka or slugify_ka(ka_name)
    ka_slug = unique_slug(model, "slug_ka", slugify_ka(ka_value), instance.pk)
    instance.slug_ka = ka_slug

    en_typed = instance.slug_en
    en_base = slugify(en_typed) if en_typed else (slugify(en_name) or ka_slug)
    instance.slug_en = unique_slug(model, "slug_en", en_base, instance.pk)
