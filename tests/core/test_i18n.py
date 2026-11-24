from pathlib import Path

import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db

KA_MO = Path(settings.BASE_DIR) / "locale" / "ka" / "LC_MESSAGES" / "django.mo"


def test_root_redirects_to_georgian_by_default(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.url == "/ka/"


def test_both_language_prefixes_resolve(client):
    assert client.get("/ka/").status_code == 200
    assert client.get("/en/").status_code == 200


def test_unknown_language_prefix_is_404(client):
    assert client.get("/fr/").status_code == 404


def test_language_cookie_is_remembered(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    response = client.get("/")
    assert response.url == "/en/"


def test_set_language_switches_prefix_and_sets_cookie(client):
    response = client.post("/i18n/setlang/", {"language": "en", "next": "/ka/"})
    assert response.status_code == 302
    assert response.url == "/en/"
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"


def test_html_lang_attribute_follows_url(client):
    assert '<html lang="en">' in client.get("/en/").content.decode()
    assert '<html lang="ka">' in client.get("/ka/").content.decode()


@pytest.mark.skipif(not KA_MO.exists(), reason="run `uv run python scripts/i18n.py compile` first")
def test_georgian_translation_is_rendered(client):
    assert "ხელნაკეთი სამკაულები ბუნებრივი ქვებით" in client.get("/ka/").content.decode()
    assert "Handmade jewelry with natural stones" in client.get("/en/").content.decode()
