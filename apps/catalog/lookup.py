"""Find objects by a translated slug, tolerating the other language's slug.

Language switching keeps the URL's slug (set_language re-resolves the path in the
new language), and shared links outlive language changes. If the slug belongs to
the other language, the caller redirects (301) to the canonical URL.
"""

from django.db.models import Model, QuerySet
from django.http import Http404
from django.utils.translation import get_language

LANGUAGES = ("ka", "en")


def by_translated_slug(queryset: QuerySet, slug: str) -> tuple[Model, bool]:
    """Return (object, needs_redirect). Raises Http404 when no language matches."""
    current = (get_language() or "ka")[:2]
    others = [lang for lang in LANGUAGES if lang != current]
    obj = queryset.filter(**{f"slug_{current}": slug}).first()
    if obj is not None:
        return obj, False
    for lang in others:
        obj = queryset.filter(**{f"slug_{lang}": slug}).first()
        if obj is not None:
            return obj, True
    raise Http404
