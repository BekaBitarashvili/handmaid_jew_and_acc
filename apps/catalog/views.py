"""Storefront views. Thin: queries live in queries.py, URL parsing in filters.py."""

from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from . import filters as shop_filters
from .lookup import by_translated_slug
from .models import Category
from .queries import category_scope, facet_options, filter_products, visible_for, with_card_data

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
    return render(request, "catalog/product_detail.html", {"product": product})
