"""Storefront template helpers: responsive product pictures, prices, labels."""

from django import template
from django.utils.translation import gettext as _

from apps.catalog.images import picture
from apps.catalog.models import Product
from apps.core.money import format_gel

register = template.Library()

# `sizes` presets matching the grid (2 / 3 / 4 columns, max 1320px) and product page.
SIZES = {
    "card": "(min-width: 80rem) 19rem, (min-width: 64rem) 22vw, (min-width: 48rem) 30vw, 46vw",
    "product": "(min-width: 64rem) 50vw, 100vw",
    "thumb": "5rem",
    "stone": "(min-width: 48rem) 33vw, 100vw",
}


@register.inclusion_tag("components/product_picture.html")
def product_picture(
    image, sizes: str = "card", *, eager: bool = False, alt: str | None = None, css: str = ""
):
    """<picture> with AVIF + WebP srcsets for a ProductImage (or None → placeholder)."""
    data = picture(image.image) if image else None
    return {
        "picture": data,
        "sizes": SIZES.get(sizes, sizes),
        "eager": eager,
        "alt": alt if alt is not None else (image.alt if image else ""),
        "css": css,
    }


@register.simple_tag
def price_text(product: Product) -> str:
    """Card price: 145 ₾, or "from 45 ₾" when variant prices differ (needs with_card_data)."""
    low = getattr(product, "min_price", product.price)
    high = getattr(product, "max_price", product.price)
    if low != high:
        return _("from %(price)s") % {"price": format_gel(low)}
    return format_gel(low)


@register.simple_tag
def card_labels(product: Product) -> list[str]:
    """Text labels above a card's name, in priority order (SPEC §9.5: no stickers)."""
    if product.status == Product.Status.SOLD:
        return [_("Sold")]
    labels = []
    if not getattr(product, "is_available", True):
        labels.append(_("Out of stock"))
    if product.is_new:
        labels.append(_("New"))
    if product.is_unique and getattr(product, "is_available", True):
        labels.append(_("One of a kind"))
    return labels


@register.filter
def availability(product: Product) -> str:
    if product.status == Product.Status.SOLD:
        return "sold"
    if not getattr(product, "is_available", False):
        return "out"
    return "unique" if product.is_unique else "in_stock"
