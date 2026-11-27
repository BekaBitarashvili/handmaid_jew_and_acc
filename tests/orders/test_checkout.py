import re

import pytest
from django.test import Client

from apps.catalog.models import ProductVariant
from apps.core.models import SiteSettings
from apps.orders.models import Order
from apps.promotions.models import Sale

from .helpers import courier, pickup, piece

pytestmark = pytest.mark.django_db
HTMX = {"HTTP_HX_REQUEST": "true"}


def text(response) -> str:
    return response.content.decode()


@pytest.fixture
def options():
    return {
        "tbilisi": courier(code="courier_tbilisi", name="Courier in Tbilisi", price=600),
        "regions": courier(code="courier_regions", name="Courier to the regions", price=1000),
        "pickup": pickup(),
    }


@pytest.fixture
def shopper(client, options):
    """A browser with one 100 ₾ piece in the cart that has opened the checkout."""
    variant = piece(price=10000, name_en="Amber necklace")
    client.post("/en/cart/add/", {"variant": variant.pk})
    page = text(client.get("/en/checkout/"))
    client.variant = variant
    client.token = re.search(r'name="checkout_token" value="(\w+)"', page).group(1)
    return client


def form(client, option, **overrides):
    values = {
        "first_name": "Nino",
        "last_name": "Beridze",
        "email": "nino@example.com",
        "phone": "555 12 34 56",
        "delivery": option.pk,
        "city": "Kutaisi",
        "address_line": "Rustaveli 1",
        "payment_method": "bog",
        "consent_terms": "on",
        "consent_privacy": "on",
        "checkout_token": client.token,
    }
    values.update(overrides)
    return {k: v for k, v in values.items() if v is not None}


class TestPage:
    def test_empty_cart_goes_back_to_the_cart(self, client, en, options):
        assert client.get("/en/checkout/")["Location"] == "/en/cart/"

    def test_sections_links_and_defaults(self, shopper, en):
        page = text(shopper.get("/en/checkout/"))
        for heading in ("Contact", "Delivery", "Gift", "Payment"):
            assert f'<legend class="checkout-legend">{heading}</legend>' in page
        assert 'href="/en/terms/"' in page and 'href="/en/privacy/"' in page
        assert re.search(r'name="consent_marketing" class="[^"]*" >', page)  # unchecked
        assert "Test mode: no real payment is made." in page
        assert re.search(r'id="pay-total"[^>]*>106 ₾<', page)  # 100 + Tbilisi 6
        assert '<meta name="robots" content="noindex' in page

    def test_cart_page_links_here(self, shopper, en):
        assert 'href="/en/checkout/"' in text(shopper.get("/en/cart/"))


class TestValidation:
    def test_required_and_consents(self, shopper, en, options):
        page = text(shopper.post("/en/checkout/", {"checkout_token": shopper.token}))
        assert "Please check the highlighted fields." in page
        assert "Please accept the terms and conditions." in page
        assert "Please confirm you have read the privacy policy." in page
        assert not Order.objects.exists()

    def test_phone_any_country_recipient_georgian(self, shopper, en, options):
        data = form(shopper, options["regions"], phone="12", recipient_phone="+49 30 12345678")
        page = text(shopper.post("/en/checkout/", data))
        assert "Enter a valid phone number." in page
        assert "must be Georgian (+995)" in page

    def test_address_needed_for_the_regions_courier(self, shopper, en, options):
        data = form(shopper, options["regions"], city="", address_line="")
        page = text(shopper.post("/en/checkout/", data))
        assert "Enter the city or village." in page and "Enter the delivery address." in page

    def test_tbilisi_needs_no_city_and_pickup_no_address(self, shopper, en, options):
        data = form(shopper, options["tbilisi"], city="")
        assert shopper.post("/en/checkout/", data).status_code == 302
        order = Order.objects.get()
        assert (order.city, order.address_line) == ("Tbilisi", "Rustaveli 1")

    def test_pickup(self, shopper, en, options):
        data = form(shopper, options["pickup"], city="", address_line="")
        assert shopper.post("/en/checkout/", data).status_code == 302
        order = Order.objects.get()
        assert (order.address_line, order.shipping_price, order.total) == ("", 0, 10000)

    def test_gift_note_limit(self, shopper, en, options):
        data = form(shopper, options["regions"], gift_note="x" * 301)
        assert "at most 300 characters" in text(shopper.post("/en/checkout/", data))


class TestPurchase:
    def test_end_to_end_with_the_fake_bank(self, shopper, en, options):
        data = form(
            shopper,
            options["regions"],
            phone="+995 555 12 34 56",
            recipient_name="Tamar",
            recipient_phone="599 11 22 33",
            gift_wrap="on",
            gift_note="Happy birthday",
            hide_prices_on_slip="on",
            consent_marketing="on",
        )
        response = shopper.post("/en/checkout/", data)
        order = Order.objects.get()
        assert (
            response["Location"] == f"/en/payments/fake/{order.payments.get().provider_order_id}/"
        )
        assert order.phone == "+995555123456" and order.recipient_phone == "+995599112233"
        assert order.language == "en" and order.consent_marketing and order.hide_prices_on_slip
        assert (order.subtotal, order.shipping_price, order.total) == (10000, 1000, 11000)
        assert order.ip_address == "127.0.0.1"

        back = shopper.post(response["Location"], {"decision": "paid"})
        page = text(shopper.get(back["Location"]))
        assert "Thank you" in page and order.number in page
        assert re.search(r'id="cart-count"[^>]*>\s*<span[^>]*>\(0\)', page)  # cart emptied

    def test_failed_payment_keeps_the_cart(self, shopper, en, options):
        response = shopper.post("/en/checkout/", form(shopper, options["regions"]))
        shopper.post(response["Location"], {"decision": "failed"})
        assert "Amber necklace" in text(shopper.get("/en/cart/"))
        shopper.variant.refresh_from_db()
        assert shopper.variant.reserved == 0

    def test_double_submit_makes_one_order(self, shopper, en, options):
        data = form(shopper, options["regions"])
        first = shopper.post("/en/checkout/", data)
        second = shopper.post("/en/checkout/", data)
        assert Order.objects.count() == 1
        assert first.status_code == second.status_code == 302
        assert second["Location"] == Order.objects.get().get_absolute_url()

    def test_new_checkout_closes_the_earlier_unpaid_order(self, shopper, en, options):
        shopper.post("/en/checkout/", form(shopper, options["regions"]))
        earlier = Order.objects.get()
        page = text(shopper.get("/en/checkout/"))
        token = re.search(r'name="checkout_token" value="(\w+)"', page).group(1)
        assert token != shopper.token
        shopper.token = token
        shopper.post("/en/checkout/", form(shopper, options["regions"]))
        earlier.refresh_from_db()
        assert (earlier.status, earlier.cancel_reason) == ("cancelled", "replaced")
        assert Order.objects.filter(status="awaiting_payment").count() == 1
        shopper.variant.refresh_from_db()
        assert shopper.variant.reserved == 1  # the same unique piece, held once

    def test_price_change_after_the_page_was_shown(self, shopper, en, options):
        Sale.objects.create(name="s", percent=30, applies_to_all=True)
        page = text(shopper.post("/en/checkout/", form(shopper, options["regions"])))
        assert "The price of Amber necklace changed" in page
        assert not Order.objects.exists()

    def test_total_seen_differs(self, shopper, en, options):
        data = form(shopper, options["regions"], expected_total=10600)
        page = text(shopper.post("/en/checkout/", data))
        assert "The total has changed" in page and not Order.objects.exists()

    def test_piece_taken_meanwhile(self, shopper, en, options):
        ProductVariant.objects.filter(pk=shopper.variant.pk).update(reserved=1)
        response = shopper.post("/en/checkout/", form(shopper, options["regions"]), follow=True)
        assert response.redirect_chain[-1][0] == "/en/cart/"
        assert "Amber necklace is out of stock right now." in text(response)  # said, not lost
        assert not Order.objects.exists()

    def test_back_after_paying_keeps_the_paid_order(self, shopper, en, options):
        from apps.payments.providers import get_provider

        shopper.post("/en/checkout/", form(shopper, options["regions"]))
        order = Order.objects.get()
        get_provider("fake").decide(order.payments.get(), "paid")  # callback never arrived
        shopper.get("/en/cart/")
        order.refresh_from_db()
        assert (order.status, order.payment_status) == ("new", "paid")

    def test_back_from_the_bank_page_releases_the_own_hold(self, shopper, en, options):
        shopper.post("/en/checkout/", form(shopper, options["regions"]))
        page = text(shopper.get("/en/checkout/"))  # browser back from the bank
        assert "Amber necklace" in page and "out of stock" not in page
        assert Order.objects.get().cancel_reason == "replaced"
        shopper.variant.refresh_from_db()
        assert shopper.variant.reserved == 0

    def test_csrf_required(self, shopper, en, options):
        strict = Client(enforce_csrf_checks=True)
        assert strict.post("/en/checkout/", form(shopper, options["regions"])).status_code == 403

    def test_rate_limit(self, shopper, en, options, settings, monkeypatch):
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
        monkeypatch.setattr("apps.orders.checkout_views.RATE_LIMIT", 0)
        response = shopper.post("/en/checkout/", form(shopper, options["regions"]))
        assert response.status_code == 429 and not Order.objects.exists()


class TestSummary:
    def test_delivery_and_gift_wrap_update_the_total(self, shopper, en, options):
        site = SiteSettings.load()
        site.gift_wrap_price = 500
        site.save()
        url = "/en/checkout/summary/"
        html = text(shopper.get(url, {"delivery": options["pickup"].pk}, **HTMX))
        assert 'name="expected_total" value="10000"' in html
        assert '<span id="pay-total" hx-swap-oob="true">100 ₾</span>' in html
        html = text(
            shopper.get(url, {"delivery": options["regions"].pk, "gift_wrap": "on"}, **HTMX)
        )
        assert 'name="expected_total" value="11500"' in html

    def test_free_delivery_over_threshold(self, shopper, en, options):
        site = SiteSettings.load()
        site.free_shipping_threshold = 10000
        site.save()
        html = text(shopper.get("/en/checkout/summary/", {"delivery": options["regions"].pk}))
        assert 'name="expected_total" value="10000"' in html
