from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant

from .factories import (
    CategoryFactory,
    ProductFactory,
    ProductImageFactory,
    ProductVariantFactory,
)

pytestmark = pytest.mark.django_db


class TestCategoryDepth:
    def test_two_levels_allowed(self):
        parent = CategoryFactory()
        child = CategoryFactory(parent=parent)
        child.full_clean()

    def test_third_level_rejected(self, en):
        child = CategoryFactory(parent=CategoryFactory())
        grandchild = CategoryFactory.build(parent=child, code="ZZZ")
        with pytest.raises(ValidationError, match="two levels"):
            grandchild.full_clean()

    def test_category_with_children_cannot_get_a_parent(self, en):
        parent = CategoryFactory()
        CategoryFactory(parent=parent)
        parent.parent = CategoryFactory()
        with pytest.raises(ValidationError, match="subcategories"):
            parent.full_clean()

    def test_code_must_be_three_capitals(self):
        category = CategoryFactory.build(code="ne1")
        with pytest.raises(ValidationError):
            category.full_clean()


class TestVariantConstraints:
    def test_reserved_cannot_exceed_stock(self):
        variant = ProductVariantFactory(stock=1)
        variant.reserved = 2
        with pytest.raises(IntegrityError), transaction.atomic():
            variant.save()

    def test_one_default_per_product(self):
        product = ProductFactory()  # already has a default variant
        with pytest.raises(IntegrityError), transaction.atomic():
            ProductVariant.objects.create(product=product, is_default=True)

    def test_available_price_and_sku(self):
        variant = ProductVariantFactory(stock=5, reserved=2, sku_suffix="M", price_override=None)
        assert variant.available == 3
        assert variant.price == variant.product.price
        assert variant.sku == f"{variant.product.sku}-M"
        variant.price_override = 9900
        assert variant.price == 9900


class TestIsNew:
    def test_auto_counts_from_published_at(self):
        product = ProductFactory.build(published_at=timezone.now() - timedelta(days=29))
        assert product.is_new
        product.published_at = timezone.now() - timedelta(days=31)
        assert not product.is_new

    def test_unpublished_is_not_new(self):
        assert not ProductFactory.build(published_at=None).is_new

    def test_owner_override(self):
        old = timezone.now() - timedelta(days=300)
        assert ProductFactory.build(published_at=old, new_badge=Product.NewBadge.YES).is_new
        fresh = timezone.now()
        assert not ProductFactory.build(published_at=fresh, new_badge=Product.NewBadge.NO).is_new


class TestImages:
    def test_primary_image_is_first_by_sort_order(self):
        product = ProductFactory()
        second = ProductImageFactory(product=product, sort_order=2)
        first = ProductImageFactory(product=product, sort_order=1)
        assert product.primary_image == first
        first.delete()
        assert Product.objects.get(pk=product.pk).primary_image == second

    def test_variant_must_belong_to_same_product(self, en):
        image = ProductImageFactory()
        image.variant = ProductVariantFactory()  # another product's variant
        with pytest.raises(ValidationError, match="another product"):
            image.clean()
