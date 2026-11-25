"""SEO for storefront pages: titles, canonical URLs, Product / BreadcrumbList JSON-LD."""

from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.models import SiteSettings
from apps.core.money import tetri_to_gel
from apps.core.seo import Seo, alternates, breadcrumbs, describe

from .images import picture
from .models import Category, Product, ProductImage, Stone

SCHEMA = "https://schema.org/"


def _brand() -> str:
    return SiteSettings.load().brand_name


def _shop_crumbs(category: Category | None) -> list[tuple[str, str]]:
    crumbs = [(_("Shop"), reverse("catalog:shop"))]
    if category is not None:
        if category.parent_id:
            crumbs.append((category.parent.name, category.parent.get_absolute_url()))
        crumbs.append((category.name, category.get_absolute_url()))
    return crumbs


def availability(product: Product) -> str:
    if product.status == Product.Status.SOLD:
        return SCHEMA + "SoldOut"
    return SCHEMA + ("InStock" if getattr(product, "is_available", False) else "OutOfStock")


def product_seo(request: HttpRequest, product: Product, images: list[ProductImage]) -> Seo:
    brand = _brand()
    canonical = request.build_absolute_uri(product.get_absolute_url())
    large = [p.large_url for p in (picture(i.image) for i in images) if p]
    condition = SCHEMA + ("UsedCondition" if product.is_preowned else "NewCondition")
    low = getattr(product, "min_price", product.price)
    high = getattr(product, "max_price", product.price)

    offer: dict = {
        "url": canonical,
        "priceCurrency": "GEL",
        "availability": availability(product),
        "itemCondition": condition,
    }
    if low == high:
        offer.update({"@type": "Offer", "price": str(tetri_to_gel(low))})
    else:
        offer.update(
            {
                "@type": "AggregateOffer",
                "lowPrice": str(tetri_to_gel(low)),
                "highPrice": str(tetri_to_gel(high)),
                "offerCount": product.variants.count(),
            }
        )

    description = describe(product.seo_description, product.short_description, product.description)
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "sku": product.sku,
        "url": canonical,
        "category": product.category.name,
        "brand": {"@type": "Brand", "name": brand},
        "itemCondition": condition,
        "offers": offer,
    }
    if description:
        data["description"] = description
    if large:
        data["image"] = [request.build_absolute_uri(url) for url in large]

    crumbs = _shop_crumbs(product.category) + [(product.name, product.get_absolute_url())]
    return Seo(
        title=product.seo_title or f"{product.name} — {product.category.name} | {brand}",
        description=description,
        canonical=canonical,
        alternates=alternates(request, product.get_absolute_url),
        noindex=not product.is_public,  # staff previews of drafts
        og_type="product",
        # Open Graph: the processed JPEG original — the most widely supported format.
        og_image=request.build_absolute_uri(images[0].image.url) if images else "",
        json_ld=[data, breadcrumbs(request, crumbs)],
    )


def listing_seo(
    request: HttpRequest, category: Category | None, *, filtered: bool, page: int
) -> Seo:
    brand = _brand()
    if category is None:
        url_for = lambda: reverse("catalog:shop")  # noqa: E731
        title = f"{_('Shop')} | {brand}"
        description = describe(_("Handmade jewelry with natural stones"))
    else:
        url_for = category.get_absolute_url
        title = f"{category.name} | {brand}"
        description = describe(category.description, _("Handmade jewelry with natural stones"))
    return Seo(
        title=title,
        description=description,
        canonical=request.build_absolute_uri(url_for()),  # never the filtered URL
        alternates=alternates(request, url_for),
        # Filter and sort combinations are endless: keep them out of the index.
        noindex=filtered or page > 1,
        json_ld=[breadcrumbs(request, _shop_crumbs(category))] if category else [],
    )


def archive_seo(request: HttpRequest, *, filtered: bool) -> Seo:
    return Seo(
        title=f"{_('Archive')} | {_brand()}",
        description=describe(_("Pieces that have found their owners.")),
        canonical=request.build_absolute_uri(reverse("catalog:archive")),
        alternates=alternates(request, lambda: reverse("catalog:archive")),
        noindex=filtered,
    )


def stones_seo(request: HttpRequest, stone: Stone | None = None) -> Seo:
    brand = _brand()
    if stone is None:
        return Seo(
            title=f"{_('Stones')} | {brand}",
            description=describe(_("The natural stones we work with.")),
            canonical=request.build_absolute_uri(reverse("catalog:stones")),
            alternates=alternates(request, lambda: reverse("catalog:stones")),
        )
    return Seo(
        title=f"{stone.name} — {_('Stones')} | {brand}",
        description=describe(stone.short_description, stone.story),
        canonical=request.build_absolute_uri(stone.get_absolute_url()),
        alternates=alternates(request, stone.get_absolute_url),
        og_image=request.build_absolute_uri(stone.image.url) if stone.image else "",
        json_ld=[
            breadcrumbs(
                request,
                [(_("Stones"), reverse("catalog:stones")), (stone.name, stone.get_absolute_url())],
            )
        ],
    )
