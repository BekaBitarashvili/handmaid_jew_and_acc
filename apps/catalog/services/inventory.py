"""All stock changes go through here, row-locked inside a transaction (CLAUDE.md).

Lifecycle of an order's pieces (SPEC §6.4–6.5):
- reserve():  checkout holds the pieces for 15 minutes (`reserved += qty`);
- commit():   payment confirmed — `stock -= qty`, `reserved -= qty`; a one-of-a-kind
              piece with nothing left becomes `sold`;
- release():  payment failed / expired — `reserved -= qty`;
- restock():  the owner cancels a paid order and returns the pieces to the shop.

Variants are always locked in id order, so two orders never wait on each other.
"""

from collections.abc import Iterable

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant


class StockReservedError(Exception):
    """A variant still has stock held by an unpaid order."""


class OutOfStock(Exception):
    """Not enough available for one of the pieces (someone else just took it)."""

    def __init__(self, variant: ProductVariant | None, variant_id: int):
        self.variant = variant
        self.variant_id = variant_id
        super().__init__(variant_id)

    @property
    def product_name(self) -> str:
        return self.variant.product.name if self.variant else ""


def _lock(variant_ids: Iterable[int]) -> dict[int, ProductVariant]:
    return {
        v.pk: v
        for v in ProductVariant.objects.select_for_update(of=("self",))
        .select_related("product")
        .filter(pk__in=set(variant_ids))
        .order_by("pk")
    }


def _totals(lines: Iterable[tuple[int, int]]) -> dict[int, int]:
    wanted: dict[int, int] = {}
    for variant_id, qty in lines:
        wanted[variant_id] = wanted.get(variant_id, 0) + qty
    return wanted


@transaction.atomic
def reserve(lines: Iterable[tuple[int, int]]) -> None:
    """Hold `(variant_id, qty)` pairs, all or nothing. Raises OutOfStock."""
    wanted = _totals(lines)
    variants = _lock(wanted)
    for variant_id, qty in wanted.items():
        variant = variants.get(variant_id)
        sellable = variant is not None and variant.product.status == Product.Status.ACTIVE
        if not sellable or variant.available < qty:
            raise OutOfStock(variant, variant_id)
    for variant_id, qty in wanted.items():
        ProductVariant.objects.filter(pk=variant_id).update(reserved=F("reserved") + qty)


@transaction.atomic
def release(lines: Iterable[tuple[int, int]]) -> None:
    """Give held pieces back (never below zero)."""
    wanted = _totals(lines)
    variants = _lock(wanted)
    for variant_id, qty in wanted.items():
        variant = variants.get(variant_id)
        if variant is not None:
            variant.reserved = max(variant.reserved - qty, 0)
            variant.save(update_fields=["reserved"])


@transaction.atomic
def commit(lines: Iterable[tuple[int, int]], *, reserved: bool = True) -> None:
    """Payment confirmed: the pieces leave the stock.

    `reserved=False` is the late payment after an expired hold: the pieces must still be
    free (raises OutOfStock otherwise, and nothing changes).
    """
    wanted = _totals(lines)
    variants = _lock(wanted)
    if not reserved:
        for variant_id, qty in wanted.items():
            variant = variants.get(variant_id)
            if variant is None or variant.available < qty:
                raise OutOfStock(variant, variant_id)
    touched: set[int] = set()
    for variant_id, qty in wanted.items():
        variant = variants[variant_id]
        variant.stock = max(variant.stock - qty, 0)
        if reserved:
            variant.reserved = max(variant.reserved - qty, 0)
        variant.save(update_fields=["stock", "reserved"])
        touched.add(variant.product_id)
    _mark_unique_sold(touched)


@transaction.atomic
def restock(lines: Iterable[tuple[int, int]]) -> None:
    """A paid order was cancelled and its pieces go back on sale."""
    wanted = _totals(lines)
    variants = _lock(wanted)
    products: set[int] = set()
    for variant_id, qty in wanted.items():
        variant = variants.get(variant_id)
        if variant is None:
            continue
        variant.stock += qty
        variant.save(update_fields=["stock"])
        products.add(variant.product_id)
    # A one-of-a-kind piece sold through this order is for sale again.
    Product.objects.filter(pk__in=products, status=Product.Status.SOLD).update(
        status=Product.Status.ACTIVE, sold_at=None, updated_at=timezone.now()
    )


def _mark_unique_sold(product_ids: set[int]) -> None:
    now = timezone.now()
    for product in Product.objects.filter(pk__in=product_ids, is_unique=True).prefetch_related(
        "variants"
    ):
        if product.status == Product.Status.ACTIVE and all(
            v.stock == 0 for v in product.variants.all()
        ):
            product.status = Product.Status.SOLD
            product.sold_at = now
            product.save(update_fields=["status", "sold_at", "updated_at"])


@transaction.atomic
def mark_sold(product: Product) -> None:
    """Owner sold the piece outside the shop: stock to 0, status sold (leaves the listings)."""
    variants = list(ProductVariant.objects.select_for_update().filter(product=product))
    if any(v.reserved for v in variants):
        raise StockReservedError(product.sku)
    for variant in variants:
        variant.stock = 0
        variant.save(update_fields=["stock"])
    product.status = Product.Status.SOLD
    product.sold_at = timezone.now()
    product.save(update_fields=["status", "sold_at", "updated_at"])
