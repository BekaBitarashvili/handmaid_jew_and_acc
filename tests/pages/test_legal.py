import pytest

from apps.pages.models import Page

pytestmark = pytest.mark.django_db


def test_terms_and_privacy_exist_as_placeholders(client, en):
    for path, title in (("/en/terms/", "Terms and conditions"), ("/en/privacy/", "Privacy policy")):
        page = client.get(path).content.decode()
        assert title in page
        assert "Text to be provided by the owner." in page
        assert '<meta name="robots" content="noindex' in page


def test_georgian_titles(client):
    assert "წესები და პირობები" in client.get("/ka/terms/").content.decode()


def test_owner_text_replaces_the_placeholder(client, en):
    Page.objects.filter(key="privacy").update(body_en="<p>We keep your data safe.</p>")
    page = client.get("/en/privacy/").content.decode()
    assert "We keep your data safe." in page and "to be provided" not in page
    assert '<meta name="robots" content="noindex' not in page


def test_footer_links_to_them(client, en):
    footer = client.get("/en/").content.decode().split("<footer", 1)[1]
    assert 'href="/en/terms/"' in footer and 'href="/en/privacy/"' in footer
