import json
import re

import pytest
from django.test import Client

from apps.catalog.models import Product
from apps.core.models import SiteSettings
from apps.orders.models import DeliveryOption
from apps.promotions.models import Sale
from tests.catalog.factories import ProductFactory

pytestmark = pytest.mark.django_db
ACTIVE = Product.Status.ACTIVE
HTMX = {"HTTP_HX_REQUEST": "true"}


def piece(price=12000, unique=True, stock=1, **kwargs):
    product = ProductFactory(status=ACTIVE, price=price, is_unique=unique, **kwargs)
    variant = product.variants.get()
    if stock != variant.stock:
        variant.stock = stock
        variant.save()
    return variant


def add(client, variant, **extra):
    data = {"variant": variant.pk, **extra}
    return client.post("/en/cart/add/", data, **HTMX)


def text(response) -> str:
    assert response.status_code == 200, response.status_code
    return response.content.decode()


class TestAdd:
    def test_htmx_fills_drawer_updates_count_and_opens(self, client, en):
        variant = piece(name_en="Amber necklace")
        response = add(client, variant)
        html = text(response)
        assert "Amber necklace" in html and "Added to your cart." in html
        assert re.search(r'<span id="cart-count"[^>]*hx-swap-oob="true">\s*<span[^>]*>\(1\)', html)
        assert 'id="cart-drawer-announcer" hx-swap-oob="innerHTML">Added to your cart.' in html
        triggers = json.loads(response["HX-Trigger"])
        assert triggers == {"cart-open": True, "cart-added": {"variant": variant.pk}}

    def test_without_js_redirects_to_the_cart_page_with_the_message(self, client, en):
        response = client.post("/en/cart/add/", {"variant": piece(name_en="Ring").pk})
        assert response.status_code == 302 and response["Location"] == "/en/cart/"
        page = text(client.get("/en/cart/"))
        assert "Added to your cart." in page and "Ring" in page

    def test_card_gets_its_in_cart_state_out_of_band(self, client, en):
        variant = piece()
        html = text(add(client, variant, source="card"))
        assert re.search(rf'<form id="cart-btn-{variant.pk}"[^>]*hx-swap-oob="true"', html)
        assert 'class="cart-button is-in-cart"' in html

    def test_unique_twice(self, client, en):
        variant = piece()
        add(client, variant)
        assert "already in your cart" in text(add(client, variant))

    def test_sold_piece_is_refused_and_not_marked_added(self, client, en):
        variant = piece()
        Product.objects.filter(pk=variant.product_id).update(status=Product.Status.SOLD)
        response = add(client, variant)
        assert "no longer available" in text(response)
        assert "cart-added" not in json.loads(response["HX-Trigger"])

    def test_unknown_variant_404(self, client, en):
        assert client.post("/en/cart/add/", {"variant": 999999}, **HTMX).status_code == 404
        assert client.post("/en/cart/add/", {"variant": "x"}, **HTMX).status_code == 404

    def test_post_only_and_csrf(self, en):
        variant = piece()
        assert Client().get("/en/cart/add/").status_code == 405
        strict = Client(enforce_csrf_checks=True)
        assert strict.post("/en/cart/add/", {"variant": variant.pk}).status_code == 403


class TestChange:
    def test_stepper_updates_the_page_and_caps(self, client, en):
        variant = piece(unique=False, stock=3, price=5000)
        add(client, variant)
        url = f"/en/cart/update/{variant.pk}/"
        html = text(client.post(url, {"qty": 5, "view": "page"}, **HTMX))
        assert "Only 3 available." in html
        assert re.search(r'class="qty-value"[^>]*>3<', html)
        assert 'id="cart-page-announcer"' in html  # page partial, not the drawer
        assert "Your cart (" not in html

    def test_stepper_in_the_drawer(self, client, en):
        variant = piece(unique=False, stock=3)
        add(client, variant)
        html = text(client.post(f"/en/cart/update/{variant.pk}/", {"qty": 2}, **HTMX))
        assert "Your cart (2)" in html

    def test_unique_has_no_stepper(self, client, en):
        add(client, piece())
        html = text(client.get("/en/cart/"))
        assert "qty-stepper" not in html and "One of a kind" in html

    def test_remove(self, client, en):
        variant = piece(name_en="Brooch")
        add(client, variant)
        html = text(client.post(f"/en/cart/remove/{variant.pk}/", {"view": "page"}, **HTMX))
        assert "Brooch was removed from your cart." in html
        assert "Your cart is empty" in html

    def test_gift_wrap_switch(self, client, en):
        site = SiteSettings.load()
        site.gift_wrap_price = 500
        site.save()
        add(client, piece(price=10000))
        html = text(client.post("/en/cart/gift-wrap/", {"gift_wrap": "1"}, **HTMX))
        assert 'role="switch" aria-checked="true"' in html
        assert re.search(r"Total</p>\s*<p class=\"price text-h3\">105 ₾", html)


class TestPages:
    def test_empty_cart_page_and_drawer(self, client, en):
        page = text(client.get("/en/cart/"))
        assert "Your cart is empty" in page and 'href="/en/shop/new/"' in page
        assert '<meta name="robots" content="noindex' in page
        assert "Your cart is empty" in text(client.get("/en/cart/drawer/", **HTMX))

    def test_sold_piece_is_announced_and_listed_apart(self, client, en):
        variant = piece(name_en="Amber necklace")
        add(client, variant)
        Product.objects.filter(pk=variant.product_id).update(status=Product.Status.SOLD)
        page = text(client.get("/en/cart/"))
        assert "Amber necklace has just been sold." in page
        assert "No longer available" in page
        assert "has just been sold" not in text(client.get("/en/cart/"))  # said once

    def test_summary_sale_savings_delivery_and_free_shipping_hint(self, client, en):
        DeliveryOption.objects.create(code="tbilisi", name="Tbilisi", price=500)
        DeliveryOption.objects.create(code="pickup", name="Pickup", requires_address=False)
        site = SiteSettings.load()
        site.free_shipping_threshold = 20000
        site.save()
        Sale.objects.create(name="s", percent=30, applies_to_all=True)
        add(client, piece(price=10000))
        page = text(client.get("/en/cart/"))
        assert "You save" in page and "30 ₾" in page
        assert "from 5 ₾" in page and "Pickup free" in page
        assert "Add 130 ₾ more for free delivery." in page
        assert 'style="width: 35%"' in page
        assert 'href="/en/checkout/"' in page

    def test_free_delivery_reached(self, client, en):
        DeliveryOption.objects.create(code="tbilisi", name="Tbilisi", price=500)
        site = SiteSettings.load()
        site.free_shipping_threshold = 10000
        site.save()
        add(client, piece(price=10000))
        page = text(client.get("/en/cart/"))
        assert "Free delivery" in page and "more for free delivery" not in page

    def test_header_count_and_card_state_follow_the_session(self, client, en):
        variant = piece(name_en="Ring")
        add(client, variant)
        shop = text(client.get("/en/shop/"))
        assert re.search(r'id="cart-count"[^>]*>\s*<span[^>]*>\(1\)', shop)
        assert 'aria-label="Ring — in your cart"' in shop

    def test_product_page_offers_the_cart_for_a_unique_piece_in_it(self, client, en):
        variant = piece(slug_en="ring")
        page = text(client.get("/en/product/ring/"))
        assert 'data-in-cart="false"' in page
        add(client, variant)
        page = text(client.get("/en/product/ring/"))
        assert 'data-in-cart="true"' in page and "In your cart" in page
