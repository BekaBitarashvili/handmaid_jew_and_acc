import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.catalog.images import picture
from apps.catalog.models import Product
from apps.catalog.queries import (
    SORT_PRICE_ASC,
    SORT_PRICE_DESC,
    ProductFilters,
    archive_products,
    category_scope,
    facet_options,
    filter_products,
    related_products,
    stones_with_counts,
    with_card_data,
)
from apps.catalog.services import inventory
from apps.catalog.services.products import prepare_product_for_save

from .factories import (
    CategoryFactory,
    MaterialFactory,
    ProductFactory,
    ProductImageFactory,
    ProductVariantFactory,
    StoneFactory,
    make_jpeg,
)

pytestmark = pytest.mark.django_db
ACTIVE, SOLD = Product.Status.ACTIVE, Product.Status.SOLD


def skus(qs):
    return [p.sku for p in qs]


class TestVisibility:
    def test_drafts_and_hidden_never_listed(self):
        shown = ProductFactory(status=ACTIVE)
        ProductFactory(status=Product.Status.DRAFT)
        ProductFactory(status=Product.Status.HIDDEN)
        assert skus(filter_products(category_scope(None), ProductFilters())) == [shown.sku]

    def test_available_only_by_default(self):
        available = ProductFactory(status=ACTIVE)
        sold = ProductFactory(status=SOLD)
        out = ProductFactory(status=ACTIVE, is_unique=False)  # default variant: 0 in stock
        assert skus(filter_products(category_scope(None), ProductFilters())) == [available.sku]
        everything = filter_products(category_scope(None), ProductFilters(available_only=False))
        assert set(skus(everything)) == {available.sku, sold.sku, out.sku}
        assert skus(everything)[0] == available.sku  # buyable pieces first

    def test_category_includes_subcategories(self):
        parent = CategoryFactory()
        child = CategoryFactory(parent=parent)
        in_child = ProductFactory(status=ACTIVE, category=child)
        ProductFactory(status=ACTIVE)  # other category
        assert skus(filter_products(category_scope(parent), ProductFilters())) == [in_child.sku]


class TestFilters:
    def test_stones_any_and_materials_combined(self):
        amber, lapis = StoneFactory(), StoneFactory()
        silver = MaterialFactory()
        a = ProductFactory(status=ACTIVE)
        a.stones.set([amber])
        a.materials.set([silver])
        b = ProductFactory(status=ACTIVE)
        b.stones.set([lapis])
        ProductFactory(status=ACTIVE)

        both = filter_products(category_scope(None), ProductFilters(stones=[amber, lapis]))
        assert set(skus(both)) == {a.sku, b.sku}
        narrowed = filter_products(
            category_scope(None), ProductFilters(stones=[amber, lapis], materials=[silver])
        )
        assert skus(narrowed) == [a.sku]

    def test_price_range_and_sort(self):
        cheap = ProductFactory(status=ACTIVE, price=4500)
        mid = ProductFactory(status=ACTIVE, price=14500)
        dear = ProductFactory(status=ACTIVE, price=21000)
        base = category_scope(None)
        ranged = filter_products(base, ProductFilters(min_price=5000, max_price=20000))
        assert skus(ranged) == [mid.sku]
        assert skus(filter_products(base, ProductFilters(sort=SORT_PRICE_ASC))) == [
            cheap.sku,
            mid.sku,
            dear.sku,
        ]
        assert skus(filter_products(base, ProductFilters(sort=SORT_PRICE_DESC)))[0] == dear.sku

    def test_stone_filter_does_not_inflate_stock(self):
        product = ProductFactory(status=ACTIVE)
        product.stones.set([StoneFactory(), StoneFactory()])
        (row,) = filter_products(
            category_scope(None), ProductFilters(stones=list(product.stones.all()))
        )
        assert row.available_qty == 1


class TestCardData:
    def test_variant_price_range(self):
        product = ProductFactory(status=ACTIVE, is_unique=False, price=4500)
        ProductVariantFactory(product=product, stock=2, price_override=6000)
        row = with_card_data(Product.objects.filter(pk=product.pk)).get()
        assert (row.min_price, row.max_price, row.available_qty) == (4500, 6000, 2)

    def test_reserved_stock_is_not_available(self):
        product = ProductFactory(status=ACTIVE)
        product.variants.update(reserved=1)
        assert not with_card_data(Product.objects.filter(pk=product.pk)).get().is_available


def test_facets_list_only_values_in_use():
    used, unused = StoneFactory(), StoneFactory()
    product = ProductFactory(status=ACTIVE, price=9900)
    product.stones.set([used])
    facets = facet_options(category_scope(None))
    assert list(facets["stones"]) == [used]
    assert unused not in facets["stones"]
    assert (facets["price_low"], facets["price_high"]) == (9900, 9900)


def test_related_prefers_shared_stones():
    stone = StoneFactory()
    product = ProductFactory(status=ACTIVE)
    product.stones.set([stone])
    same_stone = ProductFactory(status=ACTIVE)
    same_stone.stones.set([stone])
    same_category = ProductFactory(status=ACTIVE, category=product.category)
    ProductFactory(status=ACTIVE)  # unrelated
    ProductFactory(status=SOLD, category=product.category)  # not available
    assert skus(related_products(product)) == [same_stone.sku, same_category.sku]


class TestSoldAt:
    def test_mark_sold_sets_it_and_archive_orders_by_it(self):
        first, second = ProductFactory(status=ACTIVE), ProductFactory(status=ACTIVE)
        inventory.mark_sold(first)
        inventory.mark_sold(second)
        assert Product.objects.get(pk=first.pk).sold_at is not None
        assert skus(archive_products()) == [second.sku, first.sku]

    def test_status_change_in_admin_sets_and_clears_it(self):
        product = ProductFactory(status=ACTIVE)
        product.status = SOLD
        prepare_product_for_save(product, is_new=False)
        assert product.sold_at is not None
        product.status = ACTIVE
        prepare_product_for_save(product, is_new=False)
        assert product.sold_at is None


def test_stone_counts_only_available_pieces():
    stone = StoneFactory()
    for status in (ACTIVE, SOLD, Product.Status.DRAFT):
        ProductFactory(status=status).stones.set([stone])
    assert stones_with_counts().get(pk=stone.pk).available_count == 1


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
def test_picture_is_cached_and_deduplicates_small_sources(django_assert_max_num_queries):
    cache.clear()
    image = ProductImageFactory(image=make_jpeg(size=(800, 1000)))
    first = picture(image.image)
    # 1200/1800 would repeat the 800px source (no upscaling) and are dropped.
    widths = [entry.rsplit(" ", 1)[1] for entry in first.webp_srcset.split(", ")]
    assert widths == ["400w", "800w"]
    assert (first.width, first.height) == (800, 1000)
    with django_assert_max_num_queries(0):
        assert picture(image.image) == first
