"""Read-only catalog querysets for the storefront. (Writes live in services/.)

Stock and price come from correlated subqueries rather than joins: joining the
variants and also filtering by stones would multiply the sums.
"""

from dataclasses import dataclass, field
from datetime import timedelta

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
from django.utils import timezone

from .models import (
    NEW_PRODUCT_DAYS,
    Category,
    Material,
    Product,
    ProductImage,
    ProductVariant,
    Stone,
)

PUBLIC = (Product.Status.ACTIVE, Product.Status.SOLD)

SORT_NEWEST = "newest"
SORT_PRICE_ASC = "price_asc"
SORT_PRICE_DESC = "price_desc"
SORTS = (SORT_NEWEST, SORT_PRICE_ASC, SORT_PRICE_DESC)

COLLECTION_ALL = "all"
COLLECTION_NEW = "new"
COLLECTION_SALE = "sale"
COLLECTIONS = (COLLECTION_ALL, COLLECTION_NEW, COLLECTION_SALE)


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


def with_card_data(queryset: QuerySet[Product], sales: list | None = None) -> QuerySet[Product]:
    """Annotations and prefetches every product card needs, in a fixed number of queries.

    Prices: `min_price` / `max_price` are the regular variant prices; `sale_min_price` /
    `sale_max_price` apply the best running sale (equal to the regular ones when none).
    """
    from apps.promotions.services import running_sales, sale_price_expression

    sales = running_sales() if sales is None else sales
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
            # The card's cart button adds directly when there is exactly one variant.
            variant_count=Coalesce(_variant_subquery(Count("pk")), 0, output_field=_INT),
            first_variant_id=_variant_subquery(Min("pk")),
        )
        .annotate(
            sale_min_price=sale_price_expression("min_price", sales),
            sale_max_price=sale_price_expression("max_price", sales),
            is_available=Case(
                When(Q(status=Product.Status.ACTIVE) & Q(available_qty__gt=0), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
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
    query: str = ""  # simple search (Phase 3: Postgres full-text)


def category_scope(category: Category | None) -> QuerySet[Product]:
    """Listed products in a category and its subcategories (or the whole shop)."""
    qs = listed_products()
    if category is None:
        return qs.filter(category__is_active=True)
    return qs.filter(Q(category=category) | Q(category__parent=category))


def new_condition(now=None) -> Q:
    """Database version of Product.is_new: owner override, else published in the last 30 days."""
    now = now or timezone.now()
    recent = now - timedelta(days=NEW_PRODUCT_DAYS)
    return Q(new_badge=Product.NewBadge.YES) | (
        Q(new_badge=Product.NewBadge.AUTO) & Q(published_at__gte=recent)
    )


def search_condition(text: str) -> Q:
    """Name, descriptions, stones and materials in both languages (case-insensitive)."""
    condition = Q()
    for lang in ("ka", "en"):
        condition |= (
            Q(**{f"name_{lang}__icontains": text})
            | Q(**{f"short_description_{lang}__icontains": text})
            | Q(**{f"description_{lang}__icontains": text})
            | Q(
                Exists(
                    Stone.objects.filter(products=OuterRef("pk")).filter(
                        **{f"name_{lang}__icontains": text}
                    )
                )
            )
            | Q(
                Exists(
                    Material.objects.filter(products=OuterRef("pk")).filter(
                        **{f"name_{lang}__icontains": text}
                    )
                )
            )
        )
    return condition


def collection_scope(collection: str, base: QuerySet[Product]) -> QuerySet[Product]:
    """New Arrivals and Sale are filtered views of the shop (redesign §3)."""
    if collection == COLLECTION_NEW:
        return base.filter(new_condition())
    return base


def filter_products(
    base: QuerySet[Product], filters: ProductFilters, *, collection: str = COLLECTION_ALL
) -> QuerySet[Product]:
    qs = with_card_data(collection_scope(collection, base))
    if collection == COLLECTION_SALE:
        qs = qs.filter(sale_min_price__lt=F("min_price"))
    if filters.query:
        qs = qs.filter(search_condition(filters.query))
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
    # Price range and sorting use what the customer actually pays.
    if filters.min_price is not None:
        qs = qs.filter(sale_min_price__gte=filters.min_price)
    if filters.max_price is not None:
        qs = qs.filter(sale_min_price__lte=filters.max_price)
    qs = qs.filter(is_available=True)  # listings show only pieces that can be bought

    order = {
        SORT_NEWEST: ("-published_at", "-pk"),
        SORT_PRICE_ASC: ("sale_min_price", "-pk"),
        SORT_PRICE_DESC: ("-sale_min_price", "-pk"),
    }[filters.sort]
    return qs.order_by(*order)


def facet_options(base: QuerySet[Product]) -> dict:
    """Stones, materials and subcategories that actually occur in `base`, plus its price range."""
    ids = base.values("pk")
    prices = with_card_data(base).aggregate(low=Min("sale_min_price"), high=Max("sale_min_price"))
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


def chip_categories(
    base: QuerySet[Product], collection: str, selected: list[Category] | tuple = ()
) -> QuerySet[Category]:
    """Category chips for a listing. The shop shows every category; New Arrivals and Sale
    only those with a piece in that view (a subcategory's piece counts for its parent).
    A selected category stays visible even when empty, so the active filter never hides."""
    categories = top_categories()
    if collection == COLLECTION_ALL:
        return categories
    pairs = filter_products(base, ProductFilters(), collection=collection).values_list(
        "category_id", "category__parent_id"
    )
    keep = {pk for pair in pairs for pk in pair if pk}
    keep |= {c.parent_id or c.pk for c in selected}
    return categories.filter(pk__in=keep)
