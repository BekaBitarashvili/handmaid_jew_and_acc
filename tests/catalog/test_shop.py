import pytest
from django.http import QueryDict

from apps.catalog import filters as shop_filters
from apps.catalog.models import Product

from .factories import CategoryFactory, ProductFactory, StoneFactory

pytestmark = pytest.mark.django_db
ACTIVE, SOLD, DRAFT = Product.Status.ACTIVE, Product.Status.SOLD, Product.Status.DRAFT

HTMX_RESULTS = {"HX-Request": "true", "HX-Target": "results"}
HTMX_GRID = {"HX-Request": "true", "HX-Target": "product-grid"}


def html(response) -> str:
    return response.content.decode()


class TestShopPage:
    def test_lists_available_pieces_in_both_languages(self, client):
        ProductFactory(status=ACTIVE, name_ka="ქარვის ყელსაბამი", name_en="Amber necklace")
        ProductFactory(status=DRAFT, name_ka="მონახაზი", name_en="Draft piece")
        ProductFactory(status=SOLD, name_ka="გაყიდული", name_en="Sold piece")
        ka = html(client.get("/ka/shop/"))
        assert "ქარვის ყელსაბამი" in ka
        assert "მონახაზი" not in ka and "გაყიდული" not in ka
        assert "Amber necklace" in html(client.get("/en/shop/"))

    def test_including_sold_pieces_labels_them(self, client, en):
        ProductFactory(status=SOLD, name_en="Sold piece")
        page = html(client.get("/en/shop/?available=0"))
        assert "Sold piece" in page
        assert ">Sold<" in page

    def test_category_page_includes_subcategories(self, client):
        parent = CategoryFactory(name_en="Vintage", slug_en="vintage")
        child = CategoryFactory(parent=parent, name_en="Brooches", slug_en="brooches")
        ProductFactory(status=ACTIVE, category=child, name_en="Amber brooch")
        ProductFactory(status=ACTIVE, name_en="Elsewhere")
        page = html(client.get("/en/shop/vintage/"))
        assert "Amber brooch" in page and "Elsewhere" not in page
        assert 'value="brooches"' in page  # subcategory offered as a filter

    def test_other_language_slug_redirects_permanently(self, client):
        CategoryFactory(slug_ka="yelsabamebi", slug_en="necklaces")
        response = client.get("/en/shop/yelsabamebi/?stone=x")
        assert response.status_code == 301
        assert response.url == "/en/shop/necklaces/?stone=x"

    def test_unknown_category_is_404(self, client):
        assert client.get("/en/shop/nope/").status_code == 404

    def test_inactive_category_is_404(self, client):
        CategoryFactory(slug_en="hidden-cat", is_active=False)
        assert client.get("/en/shop/hidden-cat/").status_code == 404


class TestFiltering:
    def test_stone_slug_works_in_either_language(self, client):
        stone = StoneFactory(slug_ka="karva", slug_en="amber")
        ProductFactory(status=ACTIVE, name_en="With amber").stones.set([stone])
        ProductFactory(status=ACTIVE, name_en="Without")
        page = html(client.get("/en/shop/?stone=karva"))  # Georgian slug on the English page
        assert "With amber" in page and "Without" not in page

    def test_garbage_parameters_are_ignored(self, client):
        ProductFactory(status=ACTIVE)
        response = client.get("/en/shop/?min=abc&stone=nope&material=x&sort=evil&page=-4")
        assert response.status_code == 200

    def test_price_filter_in_lari(self, client):
        ProductFactory(status=ACTIVE, price=4500, name_en="Cheap one")
        ProductFactory(status=ACTIVE, price=14500, name_en="Dear one")
        page = html(client.get("/en/shop/?min=100"))
        assert "Dear one" in page and "Cheap one" not in page

    def test_htmx_returns_results_and_pushes_a_clean_url(self, client):
        stone = StoneFactory(slug_en="amber")
        ProductFactory(status=ACTIVE).stones.set([stone])
        response = client.get(
            "/en/shop/?category=&stone=amber&available=0&available=1&sort=newest&max=150.00",
            headers=HTMX_RESULTS,
        )
        body = html(response)
        assert "<html" not in body and 'id="results"' in body
        assert response["HX-Push-Url"] == "/en/shop/?stone=amber&max=150"

    def test_filter_change_resets_to_first_page(self, client):
        response = client.get("/en/shop/?sort=price_asc&page=3", headers=HTMX_RESULTS)
        assert response["HX-Push-Url"] == "/en/shop/?sort=price_asc"


class TestLoadMore:
    @pytest.fixture
    def thirteen(self):
        return [ProductFactory(status=ACTIVE) for _ in range(13)]

    def test_first_page_shows_twelve_and_a_link(self, client, thirteen):
        page = html(client.get("/en/shop/"))
        assert page.count("<article") == 12
        assert 'href="?page=2"' in page

    def test_htmx_appends_only_the_next_page(self, client, thirteen):
        body = html(client.get("/en/shop/?page=2", headers=HTMX_GRID))
        assert body.count("<article") == 1
        assert 'id="load-more"' in body and 'hx-swap-oob="true"' in body
        assert "?page=3" not in body  # nothing more to load

    def test_page_parameter_without_js_accumulates(self, client, thirteen):
        assert html(client.get("/en/shop/?page=2")).count("<article") == 13


class TestParser:
    def parse(self, query: str):
        return shop_filters.parse(QueryDict(query), category_choices=None)

    def test_defaults(self):
        filters, page = self.parse("")
        assert filters.available_only and filters.sort == "newest" and page == 1
        assert shop_filters.querystring(filters) == ""

    def test_reversed_price_range_is_swapped(self):
        filters, _ = self.parse("min=200&max=50")
        assert (filters.min_price, filters.max_price) == (5000, 20000)

    def test_page_is_bounded(self):
        assert self.parse("page=0")[1] == 1
        assert self.parse("page=999")[1] == 50

    def test_last_available_value_wins(self):
        assert self.parse("available=0&available=1")[0].available_only
        assert not self.parse("available=0")[0].available_only


class TestProductPageAccess:
    def test_draft_is_404_for_visitors_and_visible_to_staff(self, client, admin_client):
        product = ProductFactory(status=DRAFT, slug_en="secret")
        assert client.get("/en/product/secret/").status_code == 404
        assert admin_client.get("/en/product/secret/").status_code == 200
        assert product.sku

    def test_sold_product_stays_public(self, client):
        ProductFactory(status=SOLD, slug_en="gone")
        assert client.get("/en/product/gone/").status_code == 200

    def test_other_language_slug_redirects(self, client):
        ProductFactory(status=ACTIVE, slug_ka="karva", slug_en="amber")
        response = client.get("/en/product/karva/")
        assert (response.status_code, response.url) == (301, "/en/product/amber/")
