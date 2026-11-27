"""Browsers silently drop a <form> opened inside another one, so a nested form breaks both
(this hit the first product card on the shop page). Guard every page that has forms."""

import re

import pytest

from apps.catalog.models import Product
from tests.catalog.factories import ProductFactory

pytestmark = pytest.mark.django_db
TAG = re.compile(r"<(/?)form\b", re.IGNORECASE)


def max_form_depth(html: str) -> int:
    depth = deepest = 0
    for match in TAG.finditer(html):
        depth += -1 if match.group(1) else 1
        deepest = max(deepest, depth)
    assert depth == 0, "unbalanced <form> tags"
    return deepest


def test_no_page_nests_forms(client, en):
    from apps.orders.models import DeliveryOption

    DeliveryOption.objects.create(code="courier_tbilisi", name="Courier", price=600)
    product = ProductFactory(status=Product.Status.ACTIVE, slug_en="ring")
    sold = ProductFactory(status=Product.Status.SOLD, slug_en="sold-ring")
    client.post("/en/cart/add/", {"variant": product.variants.get().pk})
    client.post(f"/en/wishlist/toggle/{product.pk}/")
    client.post(f"/en/wishlist/toggle/{sold.pk}/")
    for path in (
        "/en/",
        "/en/shop/",
        "/en/shop/sale/",
        "/en/shop/new/",
        "/en/shop/?q=ring",
        "/en/product/ring/",
        "/en/product/sold-ring/",
        "/en/cart/",
        "/en/wishlist/",
        "/en/account/",
        "/en/checkout/",
    ):
        response = client.get(path, follow=True)
        assert response.status_code == 200, path
        assert max_form_depth(response.content.decode()) == 1, path
