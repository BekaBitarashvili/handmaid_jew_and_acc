import pytest
from django.template.loader import render_to_string

from apps.core.models import SiteSettings
from apps.core.templatetags.navigation import main_nav

pytestmark = pytest.mark.django_db


@pytest.fixture
def home_ka(client):
    return client.get("/ka/").content.decode()


def test_base_layout_landmarks(home_ka):
    assert 'class="skip-link"' in home_ka
    assert 'href="#main"' in home_ka
    assert "<header" in home_ka
    assert '<main id="main"' in home_ka
    assert "<footer" in home_ka


def test_assets_are_self_hosted(home_ka):
    assert "/static/dist/css/main.css" in home_ka
    assert "/static/vendor/htmx-2.0.11.min.js" in home_ka
    assert "/static/vendor/alpine-3.17.5.min.js" in home_ka
    assert "https://" not in home_ka.split("</head>")[0]  # no CDN in <head>


def test_htmx_sends_csrf_header(home_ka):
    assert 'hx-headers=\'{"X-CSRFToken": "' in home_ka


def test_preloads_fonts_for_active_language(client, home_ka):
    assert "fonts/firago-400-georgian.woff2" in home_ka
    assert "fonts/noto-serif-georgian.woff2" in home_ka
    en = client.get("/en/").content.decode()
    assert "fonts/firago-400-latin.woff2" in en
    assert "fonts/cormorant-garamond-italic-latin.woff2" in en  # English headings are italic


def test_brand_name_comes_from_site_settings(client):
    settings_obj = SiteSettings.load()
    settings_obj.brand_name = "Atelier Test"
    settings_obj.save()
    assert "Atelier Test" in client.get("/en/").content.decode()


def test_announcement_bar_only_when_set(client):
    assert "Free gift wrapping" not in client.get("/en/").content.decode()
    settings_obj = SiteSettings.load()
    settings_obj.announcement_bar_en = "Free gift wrapping"
    settings_obj.save()
    assert "Free gift wrapping" in client.get("/en/").content.decode()


def test_language_switcher_posts_current_path(home_ka):
    assert 'action="/i18n/setlang/"' in home_ka
    assert 'name="next" value="/ka/"' in home_ka
    assert 'value="en"' in home_ka


def test_nav_skips_views_that_do_not_exist_yet(rf, en):
    items = main_nav({"request": rf.get("/en/shop/")})
    labels = [item.label for item in items]
    assert "Shop" in labels
    assert "About" not in labels  # the About page arrives in Phase 2
    assert next(i for i in items if i.label == "Shop").active


def test_footer_shows_contacts_only_when_set(client):
    assert "tel:" not in client.get("/en/").content.decode()
    settings_obj = SiteSettings.load()
    settings_obj.contact_phone = "+995 555 12 34 56"
    settings_obj.save()
    assert 'href="tel:+995555123456"' in client.get("/en/").content.decode()


def test_custom_404_page(client):
    response = client.get("/en/does-not-exist/")
    assert response.status_code == 404
    assert "This page could not be found" in response.content.decode()


def test_500_page_renders_without_request_context():
    html = render_to_string("500.html")
    assert "Something went wrong" in html
    assert "/static/dist/css/main.css" in html


class TestStyleguide:
    def test_hidden_when_not_debug(self, client):
        assert client.get("/en/_styleguide/").status_code == 404

    def test_renders_in_debug(self, client, settings):
        settings.DEBUG = True
        response = client.get("/ka/_styleguide/")
        assert response.status_code == 200
        html = response.content.decode()
        assert "ხელნაკეთი სამკაულები ბუნებრივი ქვებით" in html
        assert "--color-clay-text" in html
        assert "fails AA" not in html


class TestDesignReviewPhase0:
    def test_footer_has_no_language_switcher(self, client):
        html = client.get("/ka/").content.decode()
        footer = html[html.index("<footer") :]
        assert "/i18n/setlang/" not in footer

    def test_header_still_has_language_switcher(self, client):
        html = client.get("/ka/").content.decode()
        header = html[html.index("<header") : html.index("</header>")]
        assert "/i18n/setlang/" in header

    def test_mobile_header_reserves_cart_slot(self, client):
        html = client.get("/ka/").content.decode()
        header = html[html.index("<header") : html.index("</header>")]
        # Decorative until the cart exists (Phase 1): hidden from assistive tech, not a fake link.
        slot = header[
            header.index("data-cart-placeholder") - 60 : header.index("data-cart-placeholder")
        ]
        assert 'aria-hidden="true"' in slot
        assert "<span" in slot

    def test_styleguide_marks_active_size_adjust(self, client, settings):
        settings.DEBUG = True
        html = client.get("/en/_styleguide/").content.decode()
        assert "94% · active" in html
        assert html.count(" · active") == 1
