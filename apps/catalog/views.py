"""Storefront views. Thin: queries live in queries.py, URL parsing in filters.py."""

from urllib.parse import urlencode

from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.core.money import format_gel
from apps.orders.models import DeliveryOption

from . import filters as shop_filters
from .lookup import by_translated_slug
from .models import Category, Product, Stone
from .queries import (
    archive_products,
    category_scope,
    facet_options,
    filter_products,
    public_products,
    related_products,
    stones_with_counts,
    visible_for,
    with_card_data,
)

GRID_TARGET = "product-grid"  # hx-target of "Load more"
RESULTS_TARGET = "results"  # hx-target of the filter form


def _redirect_to(obj, request: HttpRequest) -> HttpResponsePermanentRedirect:
    query = request.GET.urlencode()
    return HttpResponsePermanentRedirect(obj.get_absolute_url() + (f"?{query}" if query else ""))


def shop(request: HttpRequest, slug: str | None = None) -> HttpResponse:
    category = None
    if slug is not None:
        category, wrong_language = by_translated_slug(Category.objects.filter(is_active=True), slug)
        if wrong_language:
            return _redirect_to(category, request)

    base = category_scope(category)
    # On a category page only its subcategories can be chosen; the shop offers all.
    if category is None:
        category_choices = Category.objects.filter(is_active=True)
    else:
        category_choices = category.children.filter(is_active=True)
    filters, page = shop_filters.parse(request.GET, category_choices=category_choices)
    results = filter_products(base, filters)
    total = results.count()
    size = shop_filters.PAGE_SIZE
    has_more = total > page * size
    target = request.htmx.target if request.htmx else None

    context = {
        "category": category,
        "filters": filters,
        "page": page,
        "total": total,
        "total_text": ngettext("%(count)d piece", "%(count)d pieces", total) % {"count": total},
        "has_more": has_more,
        "next_query": shop_filters.querystring(filters, page + 1),
        "eager_count": 4 if page == 1 else 0,
    }

    if target == GRID_TARGET:
        # "Load more": only the next page of cards (+ an out-of-band button update).
        context["products"] = results[(page - 1) * size : page * size]
        context["eager_count"] = 0
        return render(request, "catalog/_cards_partial.html", context)

    # Full page or filter change: everything up to `page` (so ?page=3 shows 36 pieces).
    context["products"] = results[: page * size]
    facets = facet_options(base)
    context.update(
        {
            "facets": facets,
            "category_choices": facets["categories"]
            if category is None
            else category_choices.filter(pk__in=facets["categories"]),
            "selected": {
                "category": {c.pk for c in filters.categories},
                "stone": {s.pk for s in filters.stones},
                "material": {m.pk for m in filters.materials},
            },
            "min_value": shop_filters._lari(filters.min_price) if filters.min_price else "",
            "max_value": shop_filters._lari(filters.max_price) if filters.max_price else "",
            "active_count": shop_filters.active_count(filters),
            "title": category.name if category else _("Shop"),
        }
    )

    if target == RESULTS_TARGET:
        response = render(request, "catalog/_results_partial.html", context)
        query = shop_filters.querystring(filters)
        response["HX-Push-Url"] = request.path + (f"?{query}" if query else "")
        return response
    return render(request, "catalog/shop.html", context)


def product_detail(request: HttpRequest, slug: str) -> HttpResponse:
    product, wrong_language = by_translated_slug(with_card_data(visible_for(request.user)), slug)
    if wrong_language:
        return _redirect_to(product, request)

    images = list(product.images.all())
    variants = list(product.variants.order_by("sort_order", "pk"))
    sellable = product.status == Product.Status.ACTIVE
    first_photo_of = {}
    for index, image in enumerate(images):
        if image.variant_id is not None:
            first_photo_of.setdefault(image.variant_id, index)
    variant_data = [
        {
            "id": v.pk,
            "name": v.name or "",
            "price": format_gel(v.price),
            "available": sellable and v.available > 0,
            "image": first_photo_of.get(v.pk),
        }
        for v in variants
    ]
    selected = next(
        (d for d in variant_data if d["available"]), variant_data[0] if variant_data else None
    )

    return render(
        request,
        "catalog/product_detail.html",
        {
            "product": product,
            "images": images,
            "variants": variants,
            "variant_data": variant_data,
            "selected": selected,
            "show_variant_picker": len(variants) > 1,
            "stones": list(product.stones.all()),
            "materials": list(product.materials.all()),
            "related": related_products(product),
            "delivery_options": DeliveryOption.objects.filter(is_active=True),
            "is_preview": not product.is_public,
        },
    )


def _paged(request: HttpRequest, queryset, template: str, context: dict) -> HttpResponse:
    """Shared "Load more" paging for archive and stone pages (same partials as the shop)."""
    page = shop_filters._page(request.GET.get("page"))
    size = shop_filters.PAGE_SIZE
    total = queryset.count()
    extra_query = urlencode([(k, v) for k, v in request.GET.items() if k != "page"])
    context.update(
        {
            "total": total,
            "has_more": total > page * size,
            "next_query": (f"{extra_query}&" if extra_query else "") + f"page={page + 1}",
            "eager_count": 4 if page == 1 else 0,
        }
    )
    if request.htmx and request.htmx.target == GRID_TARGET:
        context["products"] = queryset[(page - 1) * size : page * size]
        context["eager_count"] = 0
        return render(request, "catalog/_cards_partial.html", context)
    context["products"] = queryset[: page * size]
    return render(request, template, context)


def archive(request: HttpRequest) -> HttpResponse:
    products = archive_products()
    stone = None
    if request.GET.get("stone"):
        stone = Stone.objects.filter(
            Q(slug_ka=request.GET["stone"]) | Q(slug_en=request.GET["stone"])
        ).first()
        if stone is not None:
            products = products.filter(stones=stone)
    return _paged(request, products, "catalog/archive.html", {"archive": True, "stone": stone})


def stone_list(request: HttpRequest) -> HttpResponse:
    return render(request, "catalog/stone_list.html", {"stones": stones_with_counts()})


def stone_detail(request: HttpRequest, slug: str) -> HttpResponse:
    stone, wrong_language = by_translated_slug(Stone.objects.all(), slug)
    if wrong_language:
        return _redirect_to(stone, request)
    products = (
        with_card_data(public_products().filter(stones=stone))
        .filter(is_available=True)
        .order_by("-published_at", "-pk")
    )
    has_archive = archive_products().filter(stones=stone).exists()
    return _paged(
        request,
        products,
        "catalog/stone_detail.html",
        {"stone": stone, "has_archive": has_archive},
    )
