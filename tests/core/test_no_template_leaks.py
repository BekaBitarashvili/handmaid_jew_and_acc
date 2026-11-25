"""Guard: template syntax must never reach the browser (a multi-line {# #} comment once did)."""

import pytest

from apps.catalog.models import Product
from tests.catalog.factories import ProductFactory, ProductImageFactory, StoneFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog():
    stone = StoneFactory(slug_en="amber")
    product = ProductFactory(status=Product.Status.ACTIVE, slug_en="amber-ring")
    product.stones.set([stone])
    ProductImageFactory(product=product)
    ProductFactory(status=Product.Status.SOLD)


@pytest.mark.parametrize(
    "url",
    [
        "/{lang}/",
        "/{lang}/shop/",
        "/{lang}/shop/?stone=amber",
        "/{lang}/product/amber-ring/",
        "/{lang}/no-such-page/",
    ],
)
@pytest.mark.parametrize("lang", ["ka", "en"])
def test_no_template_syntax_in_html(client, catalog, url, lang):
    html = client.get(url.format(lang=lang), follow=True).content.decode()
    # "{{BRAND}}" is the deliberate brand-name placeholder (SPEC); anything else is a leak.
    html = html.replace("{{BRAND}}", "")
    for token in ("{#", "#}", "{%", "%}", "{{", "}}"):
        assert token not in html, f"{token!r} leaked on {url.format(lang=lang)}"
