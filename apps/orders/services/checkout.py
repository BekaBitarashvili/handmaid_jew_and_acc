"""Placing an order (SPEC §6.4): re-check the cart, hold the pieces, write the snapshots."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.cart.services import Cart, SessionCart, delivery_price
from apps.catalog.images import rendition
from apps.catalog.services import inventory
from apps.core.models import SiteSettings

from ..models import DeliveryOption, Order, OrderItem, OrderStatusHistory
from ..numbers import next_order_number

RESERVATION_MINUTES = 15
logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    """Nothing was created; `messages` tell the customer why."""

    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("; ".join(messages))


class EmptyCart(CheckoutError):
    pass


class CartChanged(CheckoutError):
    """Something in the cart changed since the page was shown (sold, price, quantity)."""


class PricesChanged(CheckoutError):
    """The total differs from the one the customer saw (e.g. a delivery price changed)."""


class PieceTaken(CheckoutError):
    """Someone else got the piece in the last moment."""

    def __init__(self, product_name: str):
        self.product_name = product_name
        message = (
            _("Someone has just taken %(name)s. Please check your order.") % {"name": product_name}
            if product_name
            else _("Someone just took one of the pieces.")
        )
        super().__init__([message])


@dataclass
class CheckoutData:
    first_name: str
    last_name: str
    email: str
    phone: str  # E.164
    delivery_option: DeliveryOption
    payment_method: str
    city: str = ""
    address_line: str = ""
    delivery_notes: str = ""
    recipient_name: str = ""
    recipient_phone: str = ""  # E.164, Georgian
    gift_wrap: bool = False
    gift_note: str = ""
    hide_prices_on_slip: bool = False
    consent_terms: bool = False
    consent_privacy: bool = False
    consent_marketing: bool = False
    expected_total: int | None = None  # what the customer saw on the button
    checkout_token: str | None = None  # one per checkout form (double-submit guard)


def _thumbnail_url(image) -> str:
    """A small JPEG of the piece for the order page, emails and the slip (email clients
    handle JPEG everywhere; the original upload is far too heavy for a 56px thumbnail)."""
    if image is None:
        return ""
    try:
        thumb = rendition(image.image, 160, "jpg")
    except Exception:  # a broken file must never block an order
        logger.exception("order thumbnail failed for image %s", image.pk)
        thumb = None
    return thumb.url if thumb else image.image.url


@dataclass
class Quote:
    cart: Cart
    shipping: int

    @property
    def total(self) -> int:
        return self.cart.total + self.shipping


def quote(cart: Cart, option: DeliveryOption | None, site: SiteSettings | None = None) -> Quote:
    shipping = delivery_price(option, cart.subtotal, site) if option else 0
    return Quote(cart=cart, shipping=shipping)


def place_order(
    session_cart: SessionCart,
    data: CheckoutData,
    *,
    language: str,
    ip_address: str | None = None,
    user_agent: str = "",
) -> Order:
    """Create an order awaiting payment with its pieces held for 15 minutes.

    Raises EmptyCart / CartChanged / PricesChanged / PieceTaken; then nothing is created.
    """
    # Snapshots (names, delivery, "Tbilisi") are written in the order's language.
    with translation.override(language):
        return _place_order(session_cart, data, language, ip_address, user_agent)


def _place_order(session_cart, data, language, ip_address, user_agent) -> Order:
    if session_cart.gift_wrap != data.gift_wrap:
        session_cart.set_gift_wrap(data.gift_wrap)
    cart = session_cart.build()
    if cart.notices:
        raise CartChanged(cart.notices)
    if not cart.lines:
        raise EmptyCart([_("Your cart is empty.")])
    current = quote(cart, data.delivery_option)
    if data.expected_total is not None and data.expected_total != current.total:
        raise PricesChanged([_("The total has changed. Please check your order and try again.")])

    option = data.delivery_option
    now = timezone.now()
    with transaction.atomic():
        try:
            inventory.reserve((line.variant.pk, line.qty) for line in cart.lines)
        except inventory.OutOfStock as error:
            raise PieceTaken(error.product_name) from error

        order = Order.objects.create(
            number=next_order_number(),
            checkout_token=data.checkout_token or "",
            language=language,
            payment_method=data.payment_method,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            delivery_option=option,
            delivery_name=option.name,
            delivery_code=option.code,
            requires_address=option.requires_address,
            city=(option.fixed_city or data.city) if option.requires_address else "",
            address_line=data.address_line if option.requires_address else "",
            delivery_notes=data.delivery_notes,
            recipient_name=data.recipient_name,
            recipient_phone=data.recipient_phone,
            gift_wrap=data.gift_wrap,
            gift_note=data.gift_note,
            hide_prices_on_slip=data.hide_prices_on_slip,
            subtotal=cart.subtotal,
            savings=cart.savings,
            gift_wrap_price=cart.gift_wrap_total,
            shipping_price=current.shipping,
            total=current.total,
            consent_terms=data.consent_terms,
            consent_privacy=data.consent_privacy,
            consent_marketing=data.consent_marketing,
            consented_at=now,
            ip_address=ip_address,
            user_agent=user_agent[:300],
            reservation_expires_at=now + timedelta(minutes=RESERVATION_MINUTES),
        )
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order,
                variant=line.variant,
                product_name=line.product.name,
                variant_name=line.variant.name or "",
                sku=line.variant.sku,
                original_unit_price=line.price.original,
                unit_price=line.price.current,
                qty=line.qty,
                line_total=line.total,
                image_url=_thumbnail_url(line.image),
            )
            for line in cart.lines
        )
        OrderStatusHistory.objects.create(order=order, to_status=Order.Status.AWAITING_PAYMENT)
    return order
