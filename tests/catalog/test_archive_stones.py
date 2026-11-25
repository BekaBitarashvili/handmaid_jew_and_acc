import pytest

from apps.catalog.models import Product
from apps.catalog.services import inventory
from apps.core.models import SiteSettings

from .factories import ProductFactory, StoneFactory

pytestmark = pytest.mark.django_db
ACTIVE, SOLD = Product.Status.ACTIVE, Product.Status.SOLD
GRID = {"HX-Request": "true", "HX-Target": "product-grid"}


def html(response) -> str:
    return response.content.decode()


class TestArchive:
    def test_lists_sold_pieces_newest_sale_first_without_prices(self, client, en):
        older = ProductFactory(status=ACTIVE, name_en="Older piece", price=12300)
        newer = ProductFactory(status=ACTIVE, name_en="Newer piece")
        ProductFactory(status=ACTIVE, name_en="Still for sale")
        inventory.mark_sold(older)
        inventory.mark_sold(newer)
        page = html(client.get("/en/archive/"))
        assert page.index("Newer piece") < page.index("Older piece")
        assert "Still for sale" not in page
        assert "123" not in page  # the archive reads like a gallery: no prices
        assert "archive-photo" in page

    def test_commission_link_falls_back_to_email(self, client, en):
        settings_obj = SiteSettings.load()
        settings_obj.contact_email = "atelier@example.com"
        settings_obj.save()
        product = ProductFactory(status=SOLD)
        page = html(client.get("/en/archive/"))
        assert f"mailto:atelier@example.com?subject=A%20piece%20like%20{product.sku}" in page

    def test_no_commission_link_without_form_or_email(self, client, en):
        ProductFactory(status=SOLD)
        assert "Commission a similar piece" not in html(client.get("/en/archive/"))

    def test_filter_by_stone_and_load_more(self, client):
        stone = StoneFactory(slug_en="amber")
        for _ in range(13):
            ProductFactory(status=SOLD).stones.set([stone])
        ProductFactory(status=SOLD)  # other stone
        assert html(client.get("/en/archive/?stone=amber")).count("<article") == 12
        more = html(client.get("/en/archive/?stone=amber&page=2", headers=GRID))
        assert more.count("<article") == 1


class TestStones:
    def test_list_with_available_counts(self, client, en):
        stone = StoneFactory(name_en="Amber")
        ProductFactory(status=ACTIVE).stones.set([stone])
        ProductFactory(status=SOLD).stones.set([stone])
        page = html(client.get("/en/stones/"))
        assert "Amber" in page and "1 piece available" in page

    def test_detail_shows_story_and_available_pieces(self, client, en):
        stone = StoneFactory(slug_en="amber", name_en="Amber", story_en="<p>From the Baltic.</p>")
        ProductFactory(status=ACTIVE, name_en="Amber ring").stones.set([stone])
        ProductFactory(status=SOLD, name_en="Sold amber").stones.set([stone])
        page = html(client.get("/en/stones/amber/"))
        assert "<p>From the Baltic.</p>" in page
        assert "Amber ring" in page and "Sold amber" not in page
        assert "/en/archive/?stone=amber" in page

    def test_other_language_slug_redirects(self, client):
        StoneFactory(slug_ka="karva", slug_en="amber")
        response = client.get("/en/stones/karva/")
        assert (response.status_code, response.url) == (301, "/en/stones/amber/")
