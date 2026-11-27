"""Payment flow (SPEC §6.4–6.5). The bank's callback is the source of truth; polling and
the expiry task ask the bank too. All three end in the same idempotent order functions."""

import logging

from django.db import transaction
from django.urls import reverse
from django.utils import timezone, translation

from apps.orders.models import Order
from apps.orders.services import confirm_payment, fail_payment

from .models import Payment
from .providers import PaymentState, get_provider, provider_for_method

logger = logging.getLogger(__name__)


def start_payment(order: Order, request) -> str:
    """Create the payment with the provider; returns the URL of its hosted page."""
    provider = provider_for_method(order.payment_method)
    payment = Payment.objects.create(order=order, provider=provider.code, amount=order.total)
    with translation.override(order.language):
        return_url = request.build_absolute_uri(order.get_absolute_url())
    callback_url = request.build_absolute_uri(
        reverse("payments_api:callback", kwargs={"provider": provider.code})
    )
    created = provider.create_payment(payment, return_url=return_url, callback_url=callback_url)
    payment.provider_order_id = created.provider_order_id
    payment.raw_request = created.raw
    payment.save(update_fields=["provider_order_id", "raw_request", "updated_at"])
    return created.redirect_url


def apply_state(payment: Payment, state: PaymentState) -> Order:
    """Move payment and order on. A failure after a success is ignored (and logged)."""
    if state == PaymentState.PAID:
        if payment.status != Payment.Status.PAID:
            payment.status = Payment.Status.PAID
            payment.save(update_fields=["status", "updated_at"])
        return confirm_payment(payment.order_id)
    if state == PaymentState.FAILED:
        if payment.status == Payment.Status.PAID:
            logger.warning("failure reported after success for payment %s", payment.pk)
            return payment.order
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status", "updated_at"])
        return fail_payment(payment.order_id)
    return payment.order


@transaction.atomic
def handle_callback_data(provider_code: str, data) -> Payment:
    """A verified callback: keep its payload, then apply it. Raises Payment.DoesNotExist."""
    payment = Payment.objects.select_for_update().get(
        provider=provider_code, provider_order_id=data.provider_order_id
    )
    payment.raw_callbacks = [
        *payment.raw_callbacks,
        {"received_at": timezone.now().isoformat(), "state": str(data.state), **data.raw},
    ]
    payment.save(update_fields=["raw_callbacks", "updated_at"])
    apply_state(payment, data.state)
    return payment


def handle_callback(provider_code: str, request) -> Payment:
    """Raises InvalidCallback (bad signature / payload) or Payment.DoesNotExist."""
    data = get_provider(provider_code).verify_callback(request)
    return handle_callback_data(provider_code, data)


def sync_status(order: Order) -> Order:
    """Ask the bank about an order still awaiting payment (order page polling, expiry)."""
    if order.status != Order.Status.AWAITING_PAYMENT:
        return order
    payment = order.payments.exclude(provider_order_id="").order_by("-created_at").first()
    if payment is None:
        return order
    state = get_provider(payment.provider).fetch_status(payment.provider_order_id)
    return apply_state(payment, state)


def expire_overdue(now=None) -> int:
    """Orders whose 15-minute hold ran out: one last question to the bank, then release.
    Returns how many were expired."""
    now = now or timezone.now()
    expired = 0
    overdue = Order.objects.filter(
        status=Order.Status.AWAITING_PAYMENT, reservation_expires_at__lt=now
    ).values_list("pk", flat=True)
    for order_id in list(overdue):
        order = sync_status(Order.objects.get(pk=order_id))
        if order.status == Order.Status.AWAITING_PAYMENT:
            fail_payment(order_id, expired=True)
            expired += 1
    return expired


def refresh(order: Order) -> Order:
    """Before showing an unpaid order: ask the bank, and apply an overdue expiry right away
    (the huey task does it every minute in production; dev runs no scheduler)."""
    if order.status != Order.Status.AWAITING_PAYMENT:
        return order
    order = sync_status(order)
    expires = order.reservation_expires_at
    if order.status == Order.Status.AWAITING_PAYMENT and expires and expires < timezone.now():
        order = fail_payment(order.pk, expired=True)
    return order
