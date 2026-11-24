from pathlib import Path

import pytest
from django.conf import settings
from PIL import Image

BRAND = Path(settings.BASE_DIR) / "static" / "brand"


@pytest.mark.django_db
def test_layout_links_all_icons(client):
    html = client.get("/ka/").content.decode()
    assert 'rel="icon" href="/static/brand/favicon.ico" sizes="32x32"' in html
    assert 'href="/static/brand/favicon.svg" type="image/svg+xml"' in html
    assert 'rel="apple-touch-icon" href="/static/brand/apple-touch-icon.png"' in html


@pytest.mark.parametrize(
    ("url", "target"),
    [
        ("/favicon.ico", "/static/brand/favicon.ico"),
        ("/apple-touch-icon.png", "/static/brand/apple-touch-icon.png"),
    ],
)
def test_root_icon_urls_redirect_temporarily(client, url, target):
    response = client.get(url)
    assert response.status_code == 302  # not 301: the hashed target changes on swap
    assert response.url == target
    assert "max-age=86400" in response["Cache-Control"]


def test_generated_ico_has_all_sizes():
    with Image.open(BRAND / "favicon.ico") as ico:
        assert ico.info["sizes"] == {(16, 16), (32, 32), (48, 48)}


def test_apple_touch_icon_is_opaque_180():
    with Image.open(BRAND / "apple-touch-icon.png") as png:
        assert png.size == (180, 180)
        assert png.mode == "RGB"


def test_svg_is_the_documented_source():
    svg = (BRAND / "favicon.svg").read_text(encoding="utf-8")
    assert 'viewBox="0 0 32 32"' in svg
    assert "build_favicons.py" in svg
