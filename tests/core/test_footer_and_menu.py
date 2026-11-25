import re

import pytest

from apps.core.models import SiteSettings
from tests.catalog.factories import CategoryFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def page(client, en):
    CategoryFactory(name_en="Necklaces", slug_en="necklaces", sort_order=1)
    CategoryFactory(name_en="Earrings", slug_en="earrings", sort_order=2)
    CategoryFactory(name_en="Hidden one", slug_en="hidden-one", is_active=False)
    settings_obj = SiteSettings.load()
    settings_obj.contact_phone = "+995 555 00 00 00"
    settings_obj.contact_email = "hello@example.com"
    settings_obj.save()
    return client.get("/en/shop/").content.decode()


def section(html: str, start: str, end: str) -> str:
    return html[html.index(start) : html.index(end, html.index(start))]


class TestFooter:
    def test_three_columns(self, page):
        footer = section(page, "<footer", "</footer>")
        for heading in ('id="footer-shop"', 'id="footer-info"', ">Contact</h2>"):
            assert heading in footer

    def test_shop_column_lists_active_categories(self, page):
        shop = section(page, 'id="footer-shop"', "</nav>")
        assert 'href="/en/shop/necklaces/"' in shop and 'href="/en/shop/earrings/"' in shop
        assert "Hidden one" not in shop
        assert 'href="/en/archive/"' in shop and 'href="/en/stones/"' in shop

    def test_pages_that_do_not_exist_yet_are_plain_text(self, page):
        footer = section(page, "<footer", "</footer>")
        for label in ("About", "FAQ", "Terms", "Privacy", "Cookies"):
            assert f'<span class="text-taupe-text">{label}</span>' in footer
        assert 'href="#"' not in footer

    def test_contact_and_payment_placeholders(self, page):
        footer = section(page, "<footer", "</footer>")
        assert 'href="tel:+995555000000"' in footer
        assert 'href="mailto:hello@example.com"' in footer
        assert re.findall(r'class="payment-badge">([^<]+)<', footer) == [
            "BOG",
            "TBC",
            "VISA",
            "Mastercard",
        ]

    def test_no_language_switcher_in_footer(self, page):
        assert "/i18n/setlang/" not in section(page, "<footer", "</footer>")


class TestMobileMenu:
    def test_toggle_is_wired_for_assistive_tech(self, page):
        assert 'aria-controls="mobile-menu" aria-expanded="false"' in page
        assert 'id="mobile-menu"' in page

    def test_links_in_order(self, page):
        menu = section(page, 'id="mobile-menu"', "</nav>")
        hrefs = re.findall(r'class="menu-item"[^>]*><a href="([^"]+)"', menu)
        assert hrefs == ["/en/shop/", "/en/shop/necklaces/", "/en/shop/earrings/", "/en/stones/"]

    def test_bottom_area_has_wishlist_contact_and_language(self, page):
        menu = section(page, 'id="mobile-menu"', "</nav>")
        assert "Wishlist" in menu
        assert 'href="mailto:hello@example.com"' in menu  # Contact page not built yet
        assert "/i18n/setlang/" in menu

    def test_page_regions_can_be_made_inert(self, page):
        assert '<main id="main" class="flex-1" tabindex="-1" data-inert-with-menu>' in page
        assert '<footer class="bg-espresso text-sand" data-inert-with-menu>' in page
