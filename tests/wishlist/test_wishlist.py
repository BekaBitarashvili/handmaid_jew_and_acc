import re

import pytest
from django.core import signing
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.core.models import SiteSettings
from apps.wishlist import services
from tests.catalog.factories import ProductFactory

pytestmark = pytest.mark.django_db
ACTIVE = Product.Status.ACTIVE
HTMX = {"HTTP_HX_REQUEST": "true"}


def toggle(client, product, **extra):
    return client.post(f"/en/wishlist/toggle/{product.pk}/", extra, **HTMX)


def text(response) -> str:
    assert response.status_code == 200, response.status_code
    return response.content.decode()


def saved_ids(client) -> list[int]:
    """Read the cookie back the way the app does."""
    request = RequestFactory().get("/")
    cookie = client.cookies.get(services.COOKIE_NAME)
    request.COOKIES = {services.COOKIE_NAME: cookie.value} if cookie else {}
    return services.read_ids(request)


class TestService:
    def test_toggle_newest_first_and_limit(self):
        ids, saved = services.toggled([], 1)
        assert (ids, saved) == ([1], True)
        ids, _ = services.toggled(ids, 2)
        assert ids == [2, 1]
        ids, saved = services.toggled(ids, 1)
        assert (ids, saved) == ([2], False)
        full = list(range(1, services.MAX_ITEMS + 1))
        assert services.toggled(full, 999)[0][:2] == [999, 1]
        assert len(services.toggled(full, 999)[0]) == services.MAX_ITEMS

    def test_parse_ignores_garbage_and_duplicates(self):
        assert services.parse("3,x,3,,5") == [3, 5]

    def test_share_token_round_trip_and_tampering(self):
        token = services.share_token([4, 2])
        assert services.ids_from_token(token) == [4, 2]
        assert services.ids_from_token(token[:-2] + "xx") is None
        assert services.ids_from_token(signing.dumps("nope", salt=services.SHARE_SALT)) is None


class TestHeart:
    def test_toggle_on_and_off(self, client, en):
        product = ProductFactory(status=ACTIVE, slug_en="ring")
        html = text(toggle(client, product))
        assert 'aria-pressed="true"' in html
        assert '<span id="wishlist-count" hx-swap-oob="true">(1)</span>' in html
        assert saved_ids(client) == [product.pk]
        html = text(toggle(client, product))
        assert 'aria-pressed="false"' in html and "(0)</span>" in html
        assert saved_ids(client) == []

    def test_product_page_shows_the_saved_state(self, client, en):
        product = ProductFactory(status=ACTIVE, slug_en="ring")
        assert 'aria-pressed="false"' in text(client.get("/en/product/ring/"))
        toggle(client, product)
        page = text(client.get("/en/product/ring/"))
        assert 'aria-pressed="true"' in page
        assert 'Wishlist <span id="wishlist-count">(1)</span>' in page

    def test_heart_on_sold_piece_too(self, client, en):
        ProductFactory(status=Product.Status.SOLD, slug_en="sold-ring")
        assert 'id="wishlist-heart"' in text(client.get("/en/product/sold-ring/"))

    def test_without_js_goes_back_to_the_page(self, client, en):
        product = ProductFactory(status=ACTIVE, slug_en="ring")
        response = client.post(f"/en/wishlist/toggle/{product.pk}/", {"next": "/en/product/ring/"})
        assert response.status_code == 302 and response["Location"] == "/en/product/ring/"
        offsite = client.post(f"/en/wishlist/toggle/{product.pk}/", {"next": "https://evil.test/"})
        assert offsite["Location"] == "/en/wishlist/"

    def test_hidden_piece_cannot_be_saved(self, client, en):
        product = ProductFactory(status=Product.Status.HIDDEN)
        assert toggle(client, product).status_code == 404

    def test_tampered_cookie_is_ignored(self, client, en):
        client.cookies[services.COOKIE_NAME] = "1,2,3:forged"
        page = text(client.get("/en/account/"))
        assert "Wishlist (0)" in page

    def test_post_only(self, client, en):
        product = ProductFactory(status=ACTIVE)
        assert client.get(f"/en/wishlist/toggle/{product.pk}/").status_code == 405


class TestPage:
    def test_empty(self, client, en):
        page = text(client.get("/en/wishlist/"))
        assert "Nothing saved yet" in page and "Share your wishlist" not in page
        assert '<meta name="robots" content="noindex' in page

    def test_lists_saved_pieces_with_sold_ones_muted(self, client, en):
        site = SiteSettings.load()
        site.contact_email = "atelier@example.com"  # the commission link needs a contact
        site.save()
        ring = ProductFactory(status=ACTIVE, name_en="Ring")
        sold = ProductFactory(status=ACTIVE, name_en="Old brooch")
        toggle(client, ring)
        toggle(client, sold)
        Product.objects.filter(pk=sold.pk).update(status=Product.Status.SOLD)
        page = text(client.get("/en/wishlist/"))
        assert page.index("Old brooch") < page.index(">Ring<")  # newest first
        assert "Commission a similar piece" in page and "· Sold" in page
        assert 'action="/en/cart/add/"' in page  # the available one can go to the cart

    def test_hidden_pieces_drop_out_and_the_cookie_is_cleaned(self, client, en):
        keep = ProductFactory(status=ACTIVE)
        gone = ProductFactory(status=ACTIVE, name_en="Gone piece")
        toggle(client, keep)
        toggle(client, gone)
        Product.objects.filter(pk=gone.pk).update(status=Product.Status.HIDDEN)
        assert "Gone piece" not in text(client.get("/en/wishlist/"))
        assert saved_ids(client) == [keep.pk]

    def test_remove_from_the_page(self, client, en):
        product = ProductFactory(status=ACTIVE)
        toggle(client, product)
        html = text(toggle(client, product, view="page"))
        assert "Nothing saved yet" in html and "(0)</span>" in html

    def test_counts_in_account_page_and_menu(self, client, en):
        for _ in range(3):
            toggle(client, ProductFactory(status=ACTIVE))
        page = text(client.get("/en/account/"))
        assert "Wishlist (3)" in page and '<span id="wishlist-count">(3)</span>' in page


class TestShare:
    def test_share_link_is_read_only_and_noindex(self, client, en):
        product = ProductFactory(status=ACTIVE, name_en="Lapis ring")
        toggle(client, product)
        page = text(client.get("/en/wishlist/"))
        url = re.search(r'id="share-url"[^>]*value="(http[^"]+)"', page).group(1)
        path = url.split("testserver", 1)[1]
        shared = text(client.__class__().get(path))  # someone else opens it
        assert "Lapis ring" in shared
        assert "from your wishlist" not in shared  # no remove buttons
        assert '<meta name="robots" content="noindex' in shared

    def test_tampered_token_404(self, client, en):
        assert client.get("/en/wishlist/s/forged-token/").status_code == 404
