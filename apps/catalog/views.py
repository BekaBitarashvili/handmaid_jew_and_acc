"""Storefront views. Thin: queries live in queries.py, URL parsing in filters.py."""

from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext, pgettext_lazy

from apps.core.money import format_gel
from apps.orders.models import DeliveryOption
from apps.promotions.services import price_for, running_sales

from . import filters as shop_filters
from .lookup import by_translated_slug
from .models import Category, Product
from .queries import (
    COLLECTION_ALL,
    COLLECTION_NEW,
    COLLECTION_SALE,
    category_scope,
    chip_categories,
    facet_options,
    filter_products,
    related_products,
    visible_for,
    with_card_data,
)
from .seo import listing_seo, product_seo

GRID_TARGET = "product-grid"  # hx-target of "Load more"
RESULTS_TARGET = "results"  # hx-target of the filter form


def _redirect_to(obj, request: HttpRequest) -> HttpResponsePermanentRedirect:
    query = request.GET.urlencode()
    return HttpResponsePermanentRedirect(obj.get_absolute_url() + (f"?{query}" if query else ""))


COLLECTION_TITLES = {
    COLLECTION_ALL: pgettext_lazy("page title", "Shop"),
    COLLECTION_NEW: pgettext_lazy("page title", "New Arrivals"),
    COLLECTION_SALE: pgettext_lazy("page title", "Sale"),
}
COLLECTION_URLS = {
    COLLECTION_ALL: "catalog:shop",
    COLLECTION_NEW: "catalog:new",
    COLLECTION_SALE: "catalog:sale",
}


def listing(
    request: HttpRequest, collection: str = COLLECTION_ALL, slug: str | None = None
) -> HttpResponse:
    """Shop, a category, New Arrivals, Sale and search results: one template (redesign §3).

    A category is part of the path on the plain shop (/shop/<category>/, clean URLs for
    the home tiles) and a ?category= filter on New Arrivals and Sale.
    """
    category = None
    if slug is not None:
        category, wrong_language = by_translated_slug(Category.objects.filter(is_active=True), slug)
        if wrong_language:
            return _redirect_to(category, request)

    base = category_scope(category)
    if category is None:
        category_choices = Category.objects.filter(is_active=True)
    else:
        category_choices = category.children.filter(is_active=True)
    filters, page = shop_filters.parse(request.GET, category_choices=category_choices)
    results = filter_products(base, filters, collection=collection)
    total = results.count()
    size = shop_filters.PAGE_SIZE
    target = request.htmx.target if request.htmx else None

    context = {
        "collection": collection,
        "category": category,
        "filters": filters,
        "page": page,
        "total": total,
        "total_text": ngettext("%(count)d piece", "%(count)d pieces", total) % {"count": total},
        "has_more": total > page * size,
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
    if filters.query:
        title = _("Search: “%(query)s”") % {"query": filters.query}
    elif category is not None:
        title = category.name
    else:
        title = COLLECTION_TITLES[collection]
    selected_category = category or (filters.categories[0] if filters.categories else None)
    context.update(
        {
            "facets": facets,
            "chips": chip_categories(base, collection, filters.categories),
            "selected_category": selected_category,
            "collection_url": reverse(COLLECTION_URLS[collection]),
            "subcategories": category.children.filter(is_active=True) if category else [],
            "selected": {
                "category": {c.pk for c in filters.categories},
                "stone": {s.pk for s in filters.stones},
                "material": {m.pk for m in filters.materials},
            },
            "min_value": shop_filters._lari(filters.min_price) if filters.min_price else "",
            "max_value": shop_filters._lari(filters.max_price) if filters.max_price else "",
            "active_count": shop_filters.active_count(filters)
            - (len(filters.categories) if collection != COLLECTION_ALL else 0),
            "title": title,
            "seo": listing_seo(
                request,
                category,
                collection=collection,
                title=str(title),
                filtered=shop_filters.is_filtered(filters),
                page=page,
            ),
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
    sales = running_sales()
    prices = {v.pk: price_for(product, v.price, sales) for v in variants}
    first_photo_of = {}
    for index, image in enumerate(images):
        if image.variant_id is not None:
            first_photo_of.setdefault(image.variant_id, index)
    variant_data = [
        {
            "id": v.pk,
            "name": v.name or "",
            "price": format_gel(prices[v.pk].current),
            "old": format_gel(prices[v.pk].original) if prices[v.pk].on_sale else "",
            "off": prices[v.pk].percent_off,
            "available": sellable and v.available > 0,
            "image": first_photo_of.get(v.pk),
        }
        for v in variants
    ]
    selected_price = next(
        (prices[v.pk] for v in variants if sellable and v.available > 0),
        prices[variants[0].pk] if variants else None,
    )
    # JSON-LD: priceValidUntil when the discount has an end date.
    product.sale_ends_at = (
        selected_price.sale.ends_at if selected_price and selected_price.sale else None
    )
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
            "selected_price": selected_price,
            "show_variant_picker": len(variants) > 1,
            "stones": list(product.stones.all()),
            "materials": list(product.materials.all()),
            "related": related_products(product),
            "delivery_options": DeliveryOption.objects.filter(is_active=True),
            "is_preview": not product.is_public,
            "seo": product_seo(request, product, images),
        },
    )
