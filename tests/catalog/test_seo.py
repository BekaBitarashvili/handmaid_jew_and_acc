import json
import re

import pytest

from apps.catalog.models import Product
from apps.core.seo import json_ld

from .factories import (
    CategoryFactory,
    ProductFactory,
    ProductImageFactory,
    ProductVariantFactory,
    StoneFactory,
)

pytestmark = pytest.mark.django_db
ACTIVE, SOLD = Product.Status.ACTIVE, Product.Status.SOLD


def get(client, url) -> str:
    response = client.get(url)
    assert response.status_code == 200, url
    return response.content.decode()


def ld_blocks(html: str) -> list[dict]:
    return [
        json.loads(block)
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    ]


def product_ld(html: str) -> dict:
    return next(b for b in ld_blocks(html) if b["@type"] == "Product")


class TestProduct:
    @pytest.fixture
    def product(self):
        category = CategoryFactory(name_en="Necklaces", slug_en="necklaces")
        product = ProductFactory(
            status=ACTIVE,
            category=category,
            slug_ka="karvis-qelsabami",
            slug_en="amber-necklace",
            name_en="Amber necklace",
            short_description_en="Baltic amber on silver.",
            price=14500,
        )
        ProductImageFactory(product=product)
        return product

    def test_title_canonical_and_hreflang(self, client, en, product):
        html = get(client, "/en/product/amber-necklace/")
        assert "<title>Amber necklace — Necklaces | {{BRAND}}</title>" in html
        assert '<link rel="canonical" href="http://testserver/en/product/amber-necklace/">' in html
        # Each language points at its own slug.
        assert 'hreflang="ka" href="http://testserver/ka/product/karvis-qelsabami/"' in html
        assert 'hreflang="en" href="http://testserver/en/product/amber-necklace/"' in html
        assert 'hreflang="x-default" href="http://testserver/ka/product/karvis-qelsabami/"' in html
        assert '<meta name="description" content="Baltic amber on silver.">' in html
        assert 'property="og:type" content="product"' in html
        assert re.search(r'property="og:image" content="http://testserver/media/[^"]+\.jpg"', html)
        assert "noindex" not in html

    def test_seo_title_override(self, client, en, product):
        product.seo_title_en = "Custom title"
        product.save()
        assert "<title>Custom title</title>" in get(client, "/en/product/amber-necklace/")

    def test_product_json_ld(self, client, en, product):
        data = product_ld(get(client, "/en/product/amber-necklace/"))
        assert data["sku"] == product.sku
        assert data["offers"] == {
            "@type": "Offer",
            "url": "http://testserver/en/product/amber-necklace/",
            "priceCurrency": "GEL",
            "price": "145.00",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/NewCondition",
        }
        assert data["image"][0].startswith("http://testserver/media/")
        assert data["brand"] == {"@type": "Brand", "name": "{{BRAND}}"}

    def test_breadcrumbs(self, client, en, product):
        crumbs = next(
            b
            for b in ld_blocks(get(client, "/en/product/amber-necklace/"))
            if b["@type"] == "BreadcrumbList"
        )
        names = [item["name"] for item in crumbs["itemListElement"]]
        assert names == ["Shop", "Necklaces", "Amber necklace"]


@pytest.mark.parametrize(
    ("status", "unique", "expected"),
    [(SOLD, True, "SoldOut"), (ACTIVE, False, "OutOfStock")],  # non-unique default: 0 stock
)
def test_availability_states(client, en, status, unique, expected):
    product = ProductFactory(status=status, is_unique=unique)
    data = product_ld(get(client, f"/en/product/{product.slug_en}/"))
    assert data["offers"]["availability"] == f"https://schema.org/{expected}"
    assert data["offers"]["price"]  # price stays in JSON-LD even when sold


def test_preowned_is_used_condition(client, en):
    product = ProductFactory(status=ACTIVE, is_preowned=True)
    data = product_ld(get(client, f"/en/product/{product.slug_en}/"))
    assert (
        data["itemCondition"]
        == data["offers"]["itemCondition"]
        == ("https://schema.org/UsedCondition")
    )


def test_variant_price_range_is_an_aggregate_offer(client, en):
    product = ProductFactory(status=ACTIVE, is_unique=False, price=4500)
    ProductVariantFactory(product=product, price_override=6000)
    offers = product_ld(get(client, f"/en/product/{product.slug_en}/"))["offers"]
    assert offers["@type"] == "AggregateOffer"
    assert (offers["lowPrice"], offers["highPrice"], offers["offerCount"]) == ("45.00", "60.00", 2)


def test_draft_preview_is_noindex(admin_client, en):
    product = ProductFactory(status=Product.Status.DRAFT)
    assert 'content="noindex, follow"' in get(admin_client, f"/en/product/{product.slug_en}/")


class TestListings:
    def test_shop_is_indexable_with_clean_canonical(self, client, en):
        html = get(client, "/en/shop/")
        assert '<link rel="canonical" href="http://testserver/en/shop/">' in html
        assert "noindex" not in html
        assert 'hreflang="ka" href="http://testserver/ka/shop/"' in html

    def test_filtered_and_paged_views_are_noindex_with_base_canonical(self, client, en):
        StoneFactory(slug_en="amber")
        for url in ("/en/shop/?stone=amber", "/en/shop/?sort=price_asc", "/en/shop/?page=2"):
            html = get(client, url)
            assert 'content="noindex, follow"' in html, url
            assert '<link rel="canonical" href="http://testserver/en/shop/">' in html, url

    def test_category_hreflang_uses_translated_slugs(self, client, en):
        CategoryFactory(slug_ka="yelsabamebi", slug_en="necklaces")
        html = get(client, "/en/shop/necklaces/")
        assert 'hreflang="ka" href="http://testserver/ka/shop/yelsabamebi/"' in html


def test_pages_without_seo_still_get_hreflang(client):
    html = get(client, "/ka/")
    assert 'hreflang="en" href="http://testserver/en/"' in html
    assert 'hreflang="x-default" href="http://testserver/ka/"' in html


def test_json_ld_cannot_break_out_of_its_script():
    assert "</script>" not in json_ld({"name": "</script><script>alert(1)</script>"})
