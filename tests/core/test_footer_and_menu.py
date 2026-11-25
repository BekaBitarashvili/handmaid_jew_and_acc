"""Header, mobile menu, footer and the small pages of the redesign."""

import re

import pytest

from apps.core.models import SiteSettings

pytestmark = pytest.mark.django_db


@pytest.fixture
def page(client, en):
    settings_obj = SiteSettings.load()
    settings_obj.instagram_url = "https://instagram.com/example"
    settings_obj.pinterest_url = "https://pinterest.com/example"
    settings_obj.contact_email = "hello@example.com"
    settings_obj.contact_phone = "+995 555 00 00 00"
    settings_obj.save()
    return client.get("/en/shop/").content.decode()


def section(html: str, start: str, end: str) -> str:
    return html[html.index(start) : html.index(end, html.index(start))]


class TestHeader:
    def test_five_links_in_reference_order(self, page):
        nav = section(page, 'class="hidden desk:block"', "</nav>")
        hrefs = re.findall(r'class="nav-link"[^>]*>([^<]+)<', nav)
        assert hrefs == ["Shop", "New Arrivals", "Sale", "About", "Contact"]

    def test_only_the_current_section_is_active(self, client, en):
        html = client.get("/en/shop/new/").content.decode()
        nav = section(html, 'class="hidden desk:block"', "</nav>")
        active = re.findall(r'href="([^"]+)" class="nav-link" aria-current="page"', nav)
        assert active == ["/en/shop/new/"]  # not /en/shop/ too

    def test_icons_search_account_cart(self, page):
        header = section(page, "<header", "</header>")
        assert 'aria-controls="site-search"' in header
        assert 'href="/en/account/"' in header
        assert "data-cart-placeholder" in header and "(0)" in header

    def test_search_panel_submits_to_the_shop(self, page):
        search = section(page, 'id="site-search"', "</form>")
        assert 'action="/en/shop/"' in search and 'name="q"' in search


class TestMobileMenu:
    def test_toggle_is_wired_for_assistive_tech(self, page):
        assert 'aria-controls="mobile-menu" aria-expanded="false"' in page

    def test_five_links_then_account_wishlist_language(self, page):
        menu = section(page, 'id="mobile-menu"', "</nav>")
        links = re.findall(r'class="menu-link"[^>]*>([^<]+)<', menu)
        assert links == ["Shop", "New Arrivals", "Sale", "About", "Contact"]
        assert 'href="/en/account/"' in menu
        assert "Wishlist (0)" in menu
        assert "/i18n/setlang/" in menu

    def test_page_regions_can_be_made_inert(self, page):
        assert re.search(r'<main id="main"[^>]*data-inert-with-menu', page)
        assert re.search(r"<footer[^>]*data-inert-with-menu", page)


class TestFooter:
    def test_links_star_and_social_icons(self, page):
        footer = section(page, "<footer", "</footer>")
        assert 'href="/en/contact/"' in footer
        assert 'href="https://instagram.com/example"' in footer
        assert 'href="https://pinterest.com/example"' in footer
        assert "Facebook" not in footer  # empty link: icon hidden

    def test_pages_that_do_not_exist_yet_are_plain_text(self, page):
        footer = section(page, "<footer", "</footer>")
        for label in ("FAQ", "Terms", "Privacy", "Cookies"):
            assert f'<span class="nav-link text-taupe-text">{label}</span>' in footer
        assert 'href="#"' not in footer

    def test_payment_badges(self, page):
        footer = section(page, "<footer", "</footer>")
        assert re.findall(r'class="payment-badge">([^<]+)<', footer) == [
            "BOG",
            "TBC",
            "VISA",
            "Mastercard",
        ]

    def test_no_archive_or_stone_links(self, page):
        footer = section(page, "<footer", "</footer>")
        assert "/archive/" not in footer and "/stones/" not in footer


class TestSmallPages:
    def test_contact_page_shows_site_settings(self, client, en):
        settings_obj = SiteSettings.load()
        settings_obj.contact_email = "hello@example.com"
        settings_obj.contact_phone = "+995 555 00 00 00"
        settings_obj.save()
        html = client.get("/en/contact/").content.decode()
        assert 'href="mailto:hello@example.com"' in html
        assert 'href="tel:+995555000000"' in html

    def test_account_placeholder_explains_guest_checkout(self, client, en):
        html = client.get("/en/account/").content.decode()
        assert "Accounts are coming soon." in html
        assert "checkout works as a guest" in html
        assert "Wishlist (0)" in html

    def test_about_placeholder_is_not_indexed(self, client, en):
        html = client.get("/en/about/").content.decode()
        assert 'content="noindex, follow"' in html

    @pytest.mark.parametrize("url", ["/ka/about/", "/ka/contact/", "/ka/account/"])
    def test_georgian_pages_render(self, client, url):
        assert client.get(url).status_code == 200
