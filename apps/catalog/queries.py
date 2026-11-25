"""Read-only catalog querysets for the storefront. (Writes live in services/.)

Stock and price come from correlated subqueries rather than joins: joining the
variants and also filtering by stones would multiply the sums.
"""

from dataclasses import dataclass, field

from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    F,
    IntegerField,
    Max,
    Min,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from .models import Category, Material, Product, ProductImage, ProductVariant, Stone

PUBLIC = (Product.Status.ACTIVE, Product.Status.SOLD)

SORT_NEWEST = "newest"
SORT_PRICE_ASC = "price_asc"
SORT_PRICE_DESC = "price_desc"
SORTS = (SORT_NEWEST, SORT_PRICE_ASC, SORT_PRICE_DESC)


def _variant_subquery(aggregate):
    return Subquery(
        ProductVariant.objects.filter(product=OuterRef("pk"))
        .order_by()
        .values("product")
        .annotate(value=aggregate)
        .values("value"),
        output_field=IntegerField(),
    )


_INT = IntegerField()
_VARIANT_PRICE = Coalesce("price_override", "product__price", output_field=_INT)


def with_card_data(queryset: QuerySet[Product]) -> QuerySet[Product]:
    """Annotations and prefetches every product card needs, in a fixed number of queries."""
    return (
        queryset.select_related("category")
        .annotate(
            available_qty=Coalesce(
                _variant_subquery(Sum(F("stock") - F("reserved"))), 0, output_field=_INT
            ),
            # Effective variant prices (own price, else the product's): "from 45 ₾".
            min_price=Coalesce(
                _variant_subquery(Min(_VARIANT_PRICE)), F("price"), output_field=_INT
            ),
            max_price=Coalesce(
                _variant_subquery(Max(_VARIANT_PRICE)), F("price"), output_field=_INT
            ),
        )
        .annotate(
            is_available=Case(
                When(Q(status=Product.Status.ACTIVE) & Q(available_qty__gt=0), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        .prefetch_related(
            Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "pk")),
        )
    )


def public_products() -> QuerySet[Product]:
    """Everything a visitor may open by URL: active pieces and sold ones (kept for SEO)."""
    return Product.objects.filter(status__in=PUBLIC)


def listed_products() -> QuerySet[Product]:
    """What listings show: active pieces only. Sold pieces are never listed anywhere."""
    return Product.objects.filter(status=Product.Status.ACTIVE)


def visible_for(user) -> QuerySet[Product]:
    """Staff can preview drafts and hidden products from the admin ("View on site")."""
    if user.is_authenticated and user.is_staff:
        return Product.objects.all()
    return public_products()


@dataclass
class ProductFilters:
    categories: list[Category] = field(default_factory=list)
    stones: list[Stone] = field(default_factory=list)
    materials: list[Material] = field(default_factory=list)
    min_price: int | None = None  # tetri
    max_price: int | None = None  # tetri
    sort: str = SORT_NEWEST


def category_scope(category: Category | None) -> QuerySet[Product]:
    """Listed products in a category and its subcategories (or the whole shop)."""
    qs = listed_products()
    if category is None:
        return qs.filter(category__is_active=True)
    return qs.filter(Q(category=category) | Q(category__parent=category))


def filter_products(base: QuerySet[Product], filters: ProductFilters) -> QuerySet[Product]:
    qs = with_card_data(base)
    if filters.categories:
        qs = qs.filter(
            Q(category__in=filters.categories) | Q(category__parent__in=filters.categories)
        )
    if filters.stones:
        through = Product.stones.through
        qs = qs.filter(
            Exists(through.objects.filter(product_id=OuterRef("pk"), stone__in=filters.stones))
        )
    if filters.materials:
        through = Product.materials.through
        qs = qs.filter(
            Exists(
                through.objects.filter(product_id=OuterRef("pk"), material__in=filters.materials)
            )
        )
    if filters.min_price is not None:
        qs = qs.filter(min_price__gte=filters.min_price)
    if filters.max_price is not None:
        qs = qs.filter(min_price__lte=filters.max_price)
    qs = qs.filter(is_available=True)  # listings show only pieces that can be bought

    order = {
        SORT_NEWEST: ("-published_at", "-pk"),
        SORT_PRICE_ASC: ("min_price", "-pk"),
        SORT_PRICE_DESC: ("-min_price", "-pk"),
    }[filters.sort]
    return qs.order_by(*order)


def facet_options(base: QuerySet[Product]) -> dict:
    """Stones, materials and subcategories that actually occur in `base`, plus its price range."""
    ids = base.values("pk")
    prices = with_card_data(base).aggregate(low=Min("min_price"), high=Max("min_price"))
    return {
        "stones": Stone.objects.filter(products__in=ids).distinct(),
        "materials": Material.objects.filter(products__in=ids).distinct(),
        "categories": Category.objects.filter(is_active=True, products__in=ids)
        .distinct()
        .order_by("sort_order", "pk"),
        "price_low": prices["low"],
        "price_high": prices["high"],
    }


def related_products(product: Product, limit: int = 4) -> list[Product]:
    """Available pieces sharing the most stones first, then the same category."""
    stone_ids = list(product.stones.values_list("pk", flat=True))
    qs = (
        with_card_data(listed_products().exclude(pk=product.pk))
        .filter(is_available=True)
        .annotate(
            shared_stones=Count("stones", filter=Q(stones__in=stone_ids), distinct=True),
            same_category=Case(
                When(category=product.category_id, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        )
        .filter(Q(shared_stones__gt=0) | Q(same_category=1))
        .order_by("-shared_stones", "-same_category", "-published_at")
    )
    return list(qs[:limit])


def top_categories() -> QuerySet[Category]:
    return Category.objects.filter(is_active=True, parent__isnull=True).order_by("sort_order", "pk")
