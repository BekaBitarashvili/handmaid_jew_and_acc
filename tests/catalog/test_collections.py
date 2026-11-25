from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.services.slugs import fill_translated_slugs
from apps.promotions.models import Sale

from .factories import CategoryFactory, MaterialFactory, ProductFactory, StoneFactory

pytestmark = pytest.mark.django_db
ACTIVE = Product.Status.ACTIVE


def html(response) -> str:
    assert response.status_code == 200
    return response.content.decode()


def percent_sale(percent=30, **scope):
    sale = Sale.objects.create(name="s", percent=percent, applies_to_all=scope.pop("all_", False))
    sale.products.set(scope.get("products", []))
    sale.categories.set(scope.get("categories", []))
    return sale


class TestNewArrivals:
    def test_only_new_pieces(self, client, en):
        now = timezone.now()
        ProductFactory(status=ACTIVE, name_en="Fresh", published_at=now - timedelta(days=2))
        ProductFactory(status=ACTIVE, name_en="Older", published_at=now - timedelta(days=60))
        ProductFactory(
            status=ACTIVE,
            name_en="Forced new",
            published_at=now - timedelta(days=90),
            new_badge=Product.NewBadge.YES,
        )
        ProductFactory(
            status=ACTIVE,
            name_en="Never new",
            published_at=now,
            new_badge=Product.NewBadge.NO,
        )
        page = html(client.get("/en/shop/new/"))
        assert "Fresh" in page and "Forced new" in page
        assert "Older" not in page and "Never new" not in page
        assert '<h1 class="display">New Arrivals</h1>' in page

    def test_category_filter_on_new(self, client, en):
        necklaces = CategoryFactory(slug_en="necklaces")
        now = timezone.now()
        ProductFactory(status=ACTIVE, category=necklaces, name_en="New necklace", published_at=now)
        ProductFactory(status=ACTIVE, name_en="New other", published_at=now)
        page = html(client.get("/en/shop/new/?category=necklaces"))
        assert "New necklace" in page and "New other" not in page
        assert 'href="/en/shop/new/?category=necklaces"' in page  # chips stay inside New


class TestSale:
    def test_only_discounted_pieces_with_badge_and_prices(self, client, en):
        on_sale = ProductFactory(status=ACTIVE, name_en="Discounted", price=12000)
        ProductFactory(status=ACTIVE, name_en="Full price")
        percent_sale(30, products=[on_sale])
        page = html(client.get("/en/shop/sale/"))
        assert "Discounted" in page and "Full price" not in page
        assert "−30%" in page
        assert "price-old" in page and "120" in page and "84" in page

    def test_empty_sale_page(self, client, en):
        ProductFactory(status=ACTIVE)
        assert "No pieces are on sale right now." in html(client.get("/en/shop/sale/"))

    def test_shop_cards_show_sale_too(self, client, en):
        product = ProductFactory(status=ACTIVE, price=10000)
        percent_sale(20, all_=True)
        page = html(client.get("/en/shop/"))
        assert "−20%" in page and product.name_en in page


class TestSearch:
    def test_matches_names_descriptions_stones_materials_in_both_languages(self, client, en):
        amber = StoneFactory(name_ka="ქარვა", name_en="Amber")
        silver = MaterialFactory(name_en="Silver 925")
        ProductFactory(status=ACTIVE, name_en="Moon ring", name_ka="მთვარის ბეჭედი")
        ProductFactory(status=ACTIVE, name_en="Plain", description_en="<p>Old Tbilisi motif</p>")
        ProductFactory(status=ACTIVE, name_en="Stone thing").stones.set([amber])
        ProductFactory(status=ACTIVE, name_en="Metal thing").materials.set([silver])
        ProductFactory(status=ACTIVE, name_en="Unrelated")

        def found(query):
            return html(client.get("/en/shop/", {"q": query}))

        assert "Moon ring" in found("მთვარ")  # Georgian name, English page
        assert "Plain" in found("tbilisi")
        assert "Stone thing" in found("ქარვა")
        assert "Metal thing" in found("silver")
        page = found("silver")
        assert "Unrelated" not in page
        assert "Search: “silver”" in page
        assert 'content="noindex, follow"' in page

    def test_no_results(self, client, en):
        assert "Nothing found for this search." in html(client.get("/en/shop/?q=zzz"))


class TestChipsAndCards:
    def test_shop_chips_are_category_urls(self, client, en):
        CategoryFactory(slug_en="earrings", name_en="Earrings")
        page = html(client.get("/en/shop/"))
        assert 'href="/en/shop/earrings/"' in page

    def test_cards_have_no_labels_only_name_price_and_cart(self, client, en):
        ProductFactory(status=ACTIVE, slug_en="ring", published_at=timezone.now())
        page = html(client.get("/en/shop/"))
        assert ">New<" not in page and "One of a kind" not in page
        assert 'class="cart-button shrink-0"' in page and 'href="/en/product/ring/"' in page


class TestReservedSlugs:
    def test_category_cannot_use_new_or_sale(self):
        category = CategoryFactory.build(code="QQQ", slug_ka="new", slug_en="sale")
        with pytest.raises(ValidationError):
            category.full_clean()

    def test_generated_slugs_avoid_them(self):
        category = CategoryFactory.build(
            code="QQQ", name_ka="sale", name_en="New", slug_ka="", slug_en=""
        )
        fill_translated_slugs(category)
        assert category.slug_en == "new-items" and category.slug_ka == "sale-items"
