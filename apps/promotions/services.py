"""Effective prices under running sales (SPEC §5): the best single sale per item wins, no stacking.

The same rule exists twice, kept identical by tests:
- in Python (`price_for`) for the product page, cart and checkout;
- as SQL (`sale_price_expression`) so listings can sort and filter by the discounted price.

Percent discounts round to whole tetri, half up: 30% of 145.50 ₾ (14550 tetri) is 4365.
Fixed discounts never go below 0.
"""

from dataclasses import dataclass

from django.db.models import Case, F, IntegerField, Q, Value, When
from django.db.models.functions import Greatest, Least

from apps.catalog.models import Product

from .models import Sale


def running_sales() -> list[Sale]:
    """Running sales with their scope loaded (3 queries, once per request)."""
    sales = list(Sale.objects.running().prefetch_related("products", "categories"))
    for sale in sales:
        sale.product_ids = {p.pk for p in sale.products.all()}
        sale.category_ids = {c.pk for c in sale.categories.all()}
    return sales


def discounted(price: int, sale: Sale) -> int:
    if sale.discount_type == Sale.DiscountType.PERCENT:
        return price - (price * sale.percent + 50) // 100
    return max(price - sale.amount, 0)


def applies(sale: Sale, product: Product) -> bool:
    if sale.applies_to_all:
        return True
    if product.pk in sale.product_ids:
        return True
    category = product.category
    return category.pk in sale.category_ids or category.parent_id in sale.category_ids


@dataclass(frozen=True)
class PriceInfo:
    original: int
    current: int
    sale: Sale | None

    @property
    def on_sale(self) -> bool:
        return self.current < self.original

    @property
    def percent_off(self) -> int:
        """For the "-30%" badge (fixed discounts are shown as a percentage too)."""
        if not self.on_sale or not self.original:
            return 0
        return round((self.original - self.current) * 100 / self.original)


def price_for(product: Product, price: int, sales: list[Sale]) -> PriceInfo:
    """Best price for `price` (product or variant price) under the given running sales."""
    best, best_sale = price, None
    for sale in sales:
        if applies(sale, product):
            candidate = discounted(price, sale)
            if candidate < best:
                best, best_sale = candidate, sale
    return PriceInfo(original=price, current=best, sale=best_sale)


# --- SQL ------------------------------------------------------------------------


def _scope(sale: Sale) -> Q:
    if sale.applies_to_all:
        return Q(pk__isnull=False)
    return (
        Q(pk__in=sale.product_ids or [0])
        | Q(category_id__in=sale.category_ids or [0])
        | Q(category__parent_id__in=sale.category_ids or [0])
    )


def _discounted_sql(price: F, sale: Sale):
    if sale.discount_type == Sale.DiscountType.PERCENT:
        # Integer division on non-negative integers: same as Python's // above.
        return price - (price * Value(sale.percent) + Value(50)) / Value(100)
    return Greatest(price - Value(sale.amount), Value(0))


def sale_price_expression(price_field: str, sales: list[Sale]):
    """SQL for the best discounted value of `price_field` (an annotation or column)."""
    price = F(price_field)
    if not sales:
        return price
    options = [
        Case(
            When(_scope(sale), then=_discounted_sql(price, sale)),
            default=price,
            output_field=IntegerField(),
        )
        for sale in sales
    ]
    return options[0] if len(options) == 1 else Least(*options, output_field=IntegerField())
