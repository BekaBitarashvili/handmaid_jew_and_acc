"""Shop filters <-> query strings.

Parsing is forgiving: unknown or stale values (a stone that no longer exists,
"abc" as a price) are dropped rather than raising errors, because filter URLs
get shared and bookmarked. Slugs are accepted in either language, so a link
still works after switching language. The canonical query string leaves out
defaults, uses current-language slugs, and has a fixed parameter order.
"""

from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.db.models import Q, QuerySet
from django.http import QueryDict

from apps.core.money import gel_to_tetri, tetri_to_gel

from .models import Category, Material, Stone
from .queries import SORT_NEWEST, SORTS, ProductFilters

PAGE_SIZE = 12  # divides evenly into 2, 3 and 4 columns


def _by_slugs(queryset: QuerySet, slugs: list[str]) -> list:
    slugs = [s for s in slugs if s][:20]
    if not slugs:
        return []
    return list(queryset.filter(Q(slug_ka__in=slugs) | Q(slug_en__in=slugs)))


def _price(value: str | None) -> int | None:
    if not value:
        return None
    try:
        amount = Decimal(value.replace(",", ".").strip())
        return gel_to_tetri(amount.quantize(Decimal("0.01"))) if amount >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def _page(value: str | None) -> int:
    try:
        return max(1, min(int(value or 1), 50))
    except ValueError:
        return 1


def parse(
    params: QueryDict, *, category_choices: QuerySet[Category] | None
) -> tuple[ProductFilters, int]:
    """QueryDict -> (filters, page). `category_choices` is None where categories can't be chosen."""
    material_ids = [m for m in params.getlist("material") if m.isdigit()][:20]
    filters = ProductFilters(
        categories=_by_slugs(category_choices, params.getlist("category"))
        if category_choices is not None
        else [],
        stones=_by_slugs(Stone.objects.all(), params.getlist("stone")),
        materials=list(Material.objects.filter(pk__in=material_ids)) if material_ids else [],
        min_price=_price(params.get("min")),
        max_price=_price(params.get("max")),
        sort=params.get("sort") if params.get("sort") in SORTS else SORT_NEWEST,
    )
    if (
        filters.min_price is not None
        and filters.max_price is not None
        and filters.min_price > filters.max_price
    ):
        filters.min_price, filters.max_price = filters.max_price, filters.min_price
    return filters, _page(params.get("page"))


def _lari(tetri: int) -> str:
    amount = tetri_to_gel(tetri)
    return str(amount.quantize(Decimal("1"))) if tetri % 100 == 0 else str(amount)


def querystring(filters: ProductFilters, page: int | None = None) -> str:
    """Canonical query string without defaults, e.g. "stone=karva&max=150"."""
    pairs: list[tuple[str, str]] = []
    pairs += [("category", c.slug) for c in filters.categories]
    pairs += [("stone", s.slug) for s in filters.stones]
    pairs += [("material", str(m.pk)) for m in filters.materials]
    if filters.min_price is not None:
        pairs.append(("min", _lari(filters.min_price)))
    if filters.max_price is not None:
        pairs.append(("max", _lari(filters.max_price)))
    if filters.sort != SORT_NEWEST:
        pairs.append(("sort", filters.sort))
    if page and page > 1:
        pairs.append(("page", str(page)))
    return urlencode(pairs)


def active_count(filters: ProductFilters) -> int:
    """Number shown on the phone's "Filters (n)" button."""
    return (
        len(filters.categories)
        + len(filters.stones)
        + len(filters.materials)
        + (filters.min_price is not None)
        + (filters.max_price is not None)
    )


def is_filtered(filters: ProductFilters) -> bool:
    return active_count(filters) > 0 or filters.sort != SORT_NEWEST
