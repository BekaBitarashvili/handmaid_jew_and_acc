from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.queries import ProductFilters, category_scope, filter_products, with_card_data
from apps.promotions.models import Sale
from apps.promotions.services import discounted, price_for, running_sales
from tests.catalog.factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db
ACTIVE = Product.Status.ACTIVE


def make_sale(*, percent=None, amount=None, products=(), categories=(), all_=False, **extra):
    sale = Sale.objects.create(
        name="Test sale",
        discount_type=Sale.DiscountType.PERCENT if percent else Sale.DiscountType.FIXED,
        percent=percent,
        amount=amount,
        applies_to_all=all_,
        **extra,
    )
    sale.products.set(products)
    sale.categories.set(categories)
    return sale


class TestRules:
    def test_percent_rounds_half_up_to_whole_tetri(self):
        sale = Sale(discount_type=Sale.DiscountType.PERCENT, percent=30)
        assert discounted(14550, sale) == 14550 - 4365  # 30% of 145.50 ₾ = 43.65 ₾
        assert discounted(105, sale) == 105 - 32  # 31.5 tetri rounds up to 32

    def test_fixed_never_below_zero(self):
        sale = Sale(discount_type=Sale.DiscountType.FIXED, amount=5000)
        assert discounted(12000, sale) == 7000
        assert discounted(3000, sale) == 0

    def test_best_single_sale_wins_no_stacking(self):
        category = CategoryFactory()
        product = ProductFactory(status=ACTIVE, category=category, price=10000)
        make_sale(percent=10, all_=True)
        make_sale(percent=30, categories=[category])
        make_sale(amount=2500, products=[product])
        info = price_for(product, product.price, running_sales())
        assert (info.current, info.percent_off) == (7000, 30)  # 30% beats 10% and 25 ₾

    def test_category_sale_includes_subcategories(self):
        parent = CategoryFactory()
        product = ProductFactory(status=ACTIVE, category=CategoryFactory(parent=parent))
        make_sale(percent=20, categories=[parent])
        assert price_for(product, product.price, running_sales()).on_sale

    @pytest.mark.parametrize(
        "window",
        [
            {"is_active": False},
            {"starts_at": timezone.now() + timedelta(days=1)},  # scheduled
            {
                "starts_at": timezone.now() - timedelta(days=9),
                "ends_at": timezone.now() - timedelta(days=1),
            },
        ],
    )
    def test_only_running_sales_count(self, window):
        product = ProductFactory(status=ACTIVE)
        make_sale(percent=50, all_=True, **window)
        assert not price_for(product, product.price, running_sales()).on_sale

    def test_fixed_discount_badge_is_a_percentage(self):
        product = ProductFactory(status=ACTIVE, price=8000)
        make_sale(amount=2000, all_=True)
        assert price_for(product, product.price, running_sales()).percent_off == 25


def test_sql_and_python_agree():
    """Listings (SQL) and the product page / cart (Python) must show the same price."""
    necklaces, earrings = CategoryFactory(), CategoryFactory()
    child = CategoryFactory(parent=earrings)
    products = [
        ProductFactory(status=ACTIVE, category=necklaces, price=14550),
        ProductFactory(status=ACTIVE, category=earrings, price=105),
        ProductFactory(status=ACTIVE, category=child, price=9999),
        ProductFactory(status=ACTIVE, category=necklaces, price=3000),
        ProductFactory(status=ACTIVE, category=necklaces, price=100000),
    ]
    make_sale(percent=30, categories=[earrings])
    make_sale(amount=5000, products=[products[3], products[4]])
    make_sale(percent=7, all_=True)
    sales = running_sales()
    rows = {p.pk: p for p in with_card_data(Product.objects.all(), sales)}
    for product in products:
        assert rows[product.pk].sale_min_price == price_for(product, product.price, sales).current


def test_listings_sort_and_filter_by_the_discounted_price():
    cheap_after_sale = ProductFactory(status=ACTIVE, price=20000)
    regular = ProductFactory(status=ACTIVE, price=12000)
    make_sale(percent=50, products=[cheap_after_sale])  # 100 ₾ after the sale
    base = category_scope(None)
    assert [p.pk for p in filter_products(base, ProductFilters(sort="price_asc"))] == [
        cheap_after_sale.pk,
        regular.pk,
    ]
    in_range = filter_products(base, ProductFilters(max_price=11000))
    assert [p.pk for p in in_range] == [cheap_after_sale.pk]


class TestValidationAndAdmin:
    def test_percent_type_needs_a_percent(self):
        with pytest.raises(ValidationError):
            Sale(name="x", discount_type=Sale.DiscountType.PERCENT).full_clean()

    def test_end_must_follow_start(self):
        now = timezone.now()
        sale = Sale(name="x", percent=10, starts_at=now, ends_at=now - timedelta(hours=1))
        with pytest.raises(ValidationError):
            sale.full_clean()

    def test_admin_pages_render(self, admin_client):
        sale = make_sale(percent=30, all_=True)
        assert admin_client.get(reverse("admin:promotions_sale_changelist")).status_code == 200
        assert admin_client.get(reverse("admin:promotions_sale_add")).status_code == 200
        url = reverse("admin:promotions_sale_change", args=[sale.pk])
        html = admin_client.get(url).content.decode()
        assert 'name="banner_title_ka"' in html and 'name="banner_title_en"' in html

    def test_admin_refuses_a_sale_without_scope(self, admin_client):
        admin_client.cookies["django_language"] = "en"
        response = admin_client.post(
            reverse("admin:promotions_sale_add"),
            {
                "name": "Nothing",
                "discount_type": "percent",
                "percent": "10",
                "starts_at_0": "2026-01-01",
                "starts_at_1": "00:00:00",
                "is_active": "on",
            },
        )
        assert response.status_code == 200
        assert "Choose what the sale applies to" in response.content.decode()
        assert not Sale.objects.exists()
