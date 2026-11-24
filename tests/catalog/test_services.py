import pytest

from apps.catalog.models import Product, ProductVariant
from apps.catalog.services import inventory
from apps.catalog.services.products import (
    PublishCheck,
    duplicate_product,
    ensure_default_variant,
    publish_blockers,
    publish_blockers_for,
    set_visibility,
)

from .factories import (
    MaterialFactory,
    ProductFactory,
    ProductImageFactory,
    ProductVariantFactory,
    StoneFactory,
)

pytestmark = pytest.mark.django_db


class TestDefaultVariant:
    def test_unique_product_gets_one_in_stock(self):
        product = ProductFactory(is_unique=True)
        (variant,) = product.variants.all()
        assert (variant.is_default, variant.stock) == (True, 1)

    def test_non_unique_product_starts_at_zero(self):
        product = ProductFactory(is_unique=False)
        assert product.variants.get().stock == 0

    def test_first_variant_becomes_default_when_none_is(self):
        product = ProductFactory(is_unique=False)
        product.variants.all().delete()
        b = ProductVariantFactory(product=product, sort_order=2)
        a = ProductVariantFactory(product=product, sort_order=1)
        assert ensure_default_variant(product) == a
        assert ProductVariant.objects.get(pk=a.pk).is_default
        assert not ProductVariant.objects.get(pk=b.pk).is_default


class TestPublishRules:
    OK = PublishCheck(
        has_category=True, name_ka="ქარვა", price=100, image_count=1, images_missing_alt=0
    )

    def test_complete_product_passes(self):
        assert publish_blockers(self.OK) == []

    @pytest.mark.parametrize(
        ("change", "fragment"),
        [
            ({"name_ka": " "}, "Georgian name"),
            ({"has_category": False}, "category"),
            ({"price": 0}, "price"),
            ({"image_count": 0}, "photo"),
            ({"images_missing_alt": 1}, "screen readers"),
        ],
    )
    def test_each_rule(self, change, fragment, en):
        check = PublishCheck(**{**self.OK.__dict__, **change})
        assert any(fragment in problem for problem in publish_blockers(check))

    def test_show_is_blocked_without_photos(self):
        product = ProductFactory()
        assert set_visibility(product, True)
        product.refresh_from_db()
        assert product.status == Product.Status.DRAFT

    def test_show_sets_published_at_once(self):
        product = ProductFactory()
        ProductImageFactory(product=product)
        assert set_visibility(product, True) == []
        first = Product.objects.get(pk=product.pk).published_at
        assert first is not None
        set_visibility(product, False)
        set_visibility(product, True)
        assert Product.objects.get(pk=product.pk).published_at == first

    def test_db_check_counts_missing_alt(self):
        product = ProductFactory()
        ProductImageFactory(product=product, alt_ka="")
        assert publish_blockers_for(product)


class TestMarkSold:
    def test_moves_to_archive_with_zero_stock(self):
        product = ProductFactory(status=Product.Status.ACTIVE)
        inventory.mark_sold(product)
        product.refresh_from_db()
        assert product.status == Product.Status.SOLD
        assert product.total_stock == 0

    def test_refuses_when_reserved(self):
        product = ProductFactory()
        product.variants.update(reserved=1)
        with pytest.raises(inventory.StockReservedError):
            inventory.mark_sold(product)


class TestDuplicate:
    def test_copy_is_a_new_draft_with_everything_copied(self):
        product = ProductFactory(status=Product.Status.ACTIVE, is_unique=False)
        product.stones.set([StoneFactory()])
        product.materials.set([MaterialFactory()])
        product.variants.all().delete()
        variant = ProductVariantFactory(product=product, is_default=True, stock=4, reserved=1)
        ProductImageFactory(product=product, variant=variant)

        copy = duplicate_product(product)

        assert copy.pk != product.pk
        assert copy.sku != product.sku
        assert copy.status == Product.Status.DRAFT
        assert copy.published_at is None
        assert copy.slug_ka == f"{product.slug_ka}-copy"
        assert copy.name_ka == product.name_ka
        assert list(copy.stones.all()) == list(product.stones.all())
        assert list(copy.materials.all()) == list(product.materials.all())
        (copied_variant,) = copy.variants.all()
        assert (copied_variant.stock, copied_variant.reserved) == (4, 0)
        (copied_image,) = copy.images.all()
        assert copied_image.variant == copied_variant
