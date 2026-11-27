"""Shared builders for order tests."""

from apps.cart.services import SessionCart
from apps.catalog.models import Product
from apps.orders.models import DeliveryOption
from apps.orders.services import CheckoutData, place_order
from tests.catalog.factories import ProductFactory

ACTIVE = Product.Status.ACTIVE


class FakeSession(dict):
    modified = False


def piece(price=10000, unique=True, stock=1, **kwargs):
    product = ProductFactory(status=ACTIVE, price=price, is_unique=unique, **kwargs)
    variant = product.variants.get()
    if variant.stock != stock:
        variant.stock = stock
        variant.save()
    return variant


def courier(price=600, code="courier_regions", **kwargs):
    defaults = {"name": "Courier to the regions", "price": price, **kwargs}
    return DeliveryOption.objects.get_or_create(code=code, defaults=defaults)[0]


def pickup():
    return DeliveryOption.objects.get_or_create(
        code="pickup", defaults={"name": "Pickup", "price": 0, "requires_address": False}
    )[0]


def cart_with(*variants, qty=1):
    cart = SessionCart(FakeSession())
    for variant in variants:
        cart.add(variant, qty=qty)
    cart.build()  # the customer has seen the cart
    return cart


def data(option=None, **overrides):
    values = {
        "first_name": "Nino",
        "last_name": "Beridze",
        "email": "nino@example.com",
        "phone": "+995555123456",
        "delivery_option": option or courier(),
        "payment_method": "bog",
        "city": "Kutaisi",
        "address_line": "Rustaveli 1",
        "consent_terms": True,
        "consent_privacy": True,
    }
    values.update(overrides)
    return CheckoutData(**values)


def order_for(*variants, **overrides):
    """A placed order awaiting payment."""
    return place_order(cart_with(*variants), data(**overrides), language="en")
