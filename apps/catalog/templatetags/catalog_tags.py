"""Storefront template helpers: responsive product pictures, prices, labels."""

from urllib.parse import quote

from django import template
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.catalog.images import picture, responsive
from apps.catalog.models import Product
from apps.catalog.queries import top_categories
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


@register.inclusion_tag("components/price.html")
def price_block(product: Product, size: str = "card"):
    """Price for listings (needs with_card_data): sale = old struck through + new + badge;
    "from" when variant prices differ."""
    low = getattr(product, "min_price", product.price)
    high = getattr(product, "max_price", product.price)
    sale_low = getattr(product, "sale_min_price", low)
    sale_high = getattr(product, "sale_max_price", high)
    on_sale = sale_low < low
    return {
        "size": size,
        "on_sale": on_sale,
        "is_range": sale_low != sale_high,
        "old": format_gel(low),
        "current": format_gel(sale_low),
        "percent_off": round((low - sale_low) * 100 / low) if on_sale and low else 0,
    }


@register.simple_tag
def percent_off(product: Product) -> int:
    low = getattr(product, "min_price", product.price)
    sale_low = getattr(product, "sale_min_price", low)
    return round((low - sale_low) * 100 / low) if low and sale_low < low else 0


@register.filter
def in_set(value, collection) -> bool:
    """{{ product.first_variant_id|in_set:cart_variant_ids }}"""
    return bool(collection) and value in collection


@register.filter
def availability(product: Product) -> str:
    if product.status == Product.Status.SOLD:
        return "sold"
    if not getattr(product, "is_available", False):
        return "out"
    return "unique" if product.is_unique else "in_stock"


@register.simple_tag(takes_context=True)
def commission_url(context, product: Product | None = None) -> str:
    """Link for "Commission a similar piece".

    The request form once it exists (Phase 2); until then an e-mail to the shop with
    the SKU in the subject; an empty string when neither is available.
    """
    try:
        url = reverse("pages:commission")
        return f"{url}?product={product.sku}" if product else url
    except NoReverseMatch:
        pass
    settings_obj = context.get("site_settings")
    email = getattr(settings_obj, "contact_email", "")
    if not email:
        return ""
    subject = (_("A piece like %(sku)s") % {"sku": product.sku}) if product else _("A custom piece")
    return f"mailto:{email}?subject={quote(subject)}"


@register.simple_tag
def picture_data(image):
    """Picture data (srcsets, 1800px URL) for templates that need more than <picture>."""
    return picture(image.image) if image else None


@register.simple_tag
def nav_categories():
    """Top-level active categories for the mobile menu and footer."""
    return list(top_categories())


def _ratio(text: str) -> tuple[int, int]:
    width, height = text.split(":")
    return int(width), int(height)


@register.inclusion_tag("components/responsive_picture.html")
def responsive_picture(
    image_field,
    ratio: str = "16:7",
    *,
    mobile_image=None,
    mobile_ratio: str = "4:5",
    sizes: str = "100vw",
    eager: bool = False,
    alt: str = "",
    css: str = "",
):
    """<picture> for banners and tiles: one crop for phones (< 768px), one for larger screens."""
    phone_source = mobile_image or image_field
    return {
        "desktop": responsive(image_field, _ratio(ratio)),
        "phone": responsive(phone_source, _ratio(mobile_ratio), widths=(480, 768, 1080))
        if mobile_ratio
        else None,
        "sizes": sizes,
        "eager": eager,
        "alt": alt,
        "css": css,
    }
