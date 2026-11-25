"""All stock changes go through here, row-locked inside a transaction (CLAUDE.md).

Phase 1a only needs "mark sold"; reservations and payment confirmation (1d)
add reserve / release / commit functions in this module.
"""

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant


class StockReservedError(Exception):
    """A variant still has stock held by an unpaid order."""


@transaction.atomic
def mark_sold(product: Product) -> None:
    """Owner sold the piece outside the shop: stock to 0, product to the archive."""
    variants = list(ProductVariant.objects.select_for_update().filter(product=product))
    if any(v.reserved for v in variants):
        raise StockReservedError(product.sku)
    for variant in variants:
        variant.stock = 0
        variant.save(update_fields=["stock"])
    product.status = Product.Status.SOLD
    product.sold_at = timezone.now()
    product.save(update_fields=["status", "sold_at", "updated_at"])
