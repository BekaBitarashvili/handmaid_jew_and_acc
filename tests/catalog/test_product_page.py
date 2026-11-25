import json
import re

import pytest

from apps.catalog.models import Product
from apps.core.models import SiteSettings
from apps.orders.models import DeliveryOption

from .factories import ProductFactory, ProductImageFactory, ProductVariantFactory, StoneFactory

pytestmark = pytest.mark.django_db
ACTIVE, SOLD = Product.Status.ACTIVE, Product.Status.SOLD


@pytest.fixture
def shop_email():
    settings_obj = SiteSettings.load()
    settings_obj.contact_email = "atelier@example.com"
    settings_obj.save()


def page(client, product, lang="en") -> str:
    response = client.get(
        f"/{lang}/product/{product.slug_en if lang == 'en' else product.slug_ka}/"
    )
    assert response.status_code == 200
    return response.content.decode()


def variant_json(html: str) -> list[dict]:
    match = re.search(
        r'<script id="variant-data" type="application/json">(.*?)</script>', html, re.S
    )
    return json.loads(match.group(1))


class TestAvailablePiece:
    def test_one_of_a_kind(self, client, en, shop_email):
        product = ProductFactory(status=ACTIVE, price=14500)
        ProductImageFactory(product=product)
        html = page(client, product)
        assert "One of a kind — only 1" in html
        assert "145" in html
        assert re.search(r"<button[^>]*disabled[^>]*>\s*Add to cart", html)  # placeholder until 1c
        assert "Commission a similar piece" not in html  # only for sold / out of stock
        assert 'fetchpriority="high"' in html  # first photo is the LCP image

    def test_no_variant_picker_for_a_single_variant(self, client, en):
        html = page(client, ProductFactory(status=ACTIVE))
        assert 'name="variant"' not in html


class TestSoldPiece:
    def test_stays_live_with_muted_price_and_commission(self, client, en, shop_email):
        product = ProductFactory(status=SOLD, price=12000)
        html = page(client, product)
        assert re.search(r'class="price text-h3 text-sold-text">120', html)
        assert ">Sold<" in html
        assert "Add to cart" not in html
        assert f"mailto:atelier@example.com?subject=A%20piece%20like%20{product.sku}" in html

    def test_commission_hidden_when_owner_disallows(self, client, en, shop_email):
        html = page(client, ProductFactory(status=SOLD, allow_commission_request=False))
        assert "Commission a similar piece" not in html


class TestVariants:
    @pytest.fixture
    def scarf(self):
        product = ProductFactory(status=ACTIVE, is_unique=False, price=8500)
        product.variants.all().delete()
        ProductVariantFactory(
            product=product, name_en="Beige", stock=0, sort_order=1, is_default=True
        )
        olive = ProductVariantFactory(
            product=product, name_en="Olive", stock=2, sort_order=2, price_override=9000
        )
        ProductImageFactory(product=product, sort_order=1)
        ProductImageFactory(product=product, sort_order=2, variant=olive)
        return product

    def test_picker_data_and_first_available_selected(self, client, en, scarf):
        html = page(client, scarf)
        data = variant_json(html)
        assert [(v["name"], v["available"], v["image"]) for v in data] == [
            ("Beige", False, None),
            ("Olive", True, 1),
        ]
        assert data[1]["price"] == "90 ₾"
        assert html.count('name="variant"') == 2
        assert "is-unavailable" in html  # Beige is out of stock

    def test_out_of_stock_product_offers_commission(self, client, en, shop_email):
        product = ProductFactory(status=ACTIVE, is_unique=False)  # default variant: 0 in stock
        html = page(client, product)
        assert "Out of stock" in html
        assert "Add to cart" not in html
        assert "Commission a similar piece" in html


class TestAccordions:
    def test_sections_and_links(self, client, en):
        stone = StoneFactory(name_en="Amber", slug_en="amber")
        product = ProductFactory(
            status=ACTIVE,
            description_en="<p>Long description.</p>",
            story_en="",
            care_instructions_en="Keep dry.",
            dimensions_en="Length 45 cm",
            weight_g=12,
        )
        product.stones.set([stone])
        DeliveryOption.objects.create(code="pickup", name_en="Pickup", price=0)
        DeliveryOption.objects.create(code="courier", name_en="Courier", price=700)
        html = page(client, product)
        assert '<details class="accordion" open>' in html  # description open by default
        assert "<p>Long description.</p>" in html
        assert ">Story<" not in html  # empty sections are left out
        assert 'href="/en/stones/amber/"' in html
        assert "Length 45 cm" in html and "12 g" in html
        assert "Pickup" in html and "7 ₾" in html
        assert "0 ₾" not in html  # unset (0) delivery prices are not shown


def test_related_pieces(client, en):
    stone = StoneFactory()
    product = ProductFactory(status=ACTIVE)
    product.stones.set([stone])
    ProductFactory(status=ACTIVE, name_en="Sibling piece").stones.set([stone])
    assert "Sibling piece" in page(client, product)


def test_staff_preview_banner(admin_client, en):
    product = ProductFactory(status=Product.Status.DRAFT)
    html = admin_client.get(f"/en/product/{product.slug_en}/").content.decode()
    assert "not visible in the shop" in html


def test_georgian_page(client):
    product = ProductFactory(status=ACTIVE, name_ka="ქარვის ყელსაბამი")
    assert "ქარვის ყელსაბამი" in page(client, product, lang="ka")
