"""Manual status changes by the owner (SPEC §7). Only the transitions below are allowed;
each one is logged and the customer gets the matching email."""

from django.db import transaction
from django.utils.translation import gettext as _

from apps.catalog.services import inventory

from ..models import Order
from ..notifications import Event, notify
from .lifecycle import history, lines

S = Order.Status

TRANSITIONS: dict[str, tuple[str, ...]] = {
    S.AWAITING_PAYMENT: (S.CANCELLED,),
    S.NEW: (S.PROCESSING, S.CANCELLED),
    S.PROCESSING: (S.SHIPPED, S.CANCELLED),
    S.SHIPPED: (S.DELIVERED, S.CANCELLED),
    S.DELIVERED: (),
    S.CANCELLED: (),
}
EMAILS = {S.SHIPPED: Event.SHIPPED, S.DELIVERED: Event.DELIVERED}


class InvalidTransition(Exception):
    pass


def allowed_next(order: Order) -> tuple[str, ...]:
    return TRANSITIONS.get(order.status, ())


@transaction.atomic
def change_status(
    order: Order,
    to: str,
    *,
    by=None,
    note: str = "",
    customer_note: str | None = None,
    return_to_shop: bool = True,
) -> Order:
    """Move the order on. Cancelling an unpaid order releases its held pieces; cancelling a
    paid one returns the pieces to the shop unless the owner unticks that."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if to not in allowed_next(order):
        raise InvalidTransition(f"{order.status} -> {to}")
    previous = order.status
    was_paid = order.payment_status == Order.PaymentStatus.PAID

    if to == S.CANCELLED:
        if previous == S.AWAITING_PAYMENT:
            inventory.release(lines(order))
            order.payment_status = Order.PaymentStatus.FAILED
            order.reservation_expires_at = None
        elif return_to_shop:
            inventory.restock(lines(order))
        order.cancel_reason = Order.CancelReason.OWNER
    if customer_note is not None:
        order.customer_note = customer_note.strip()
    order.status = to
    order.save()
    history(order, previous, note=note.strip(), by=by)

    if to in EMAILS:
        notify(order, EMAILS[to])
    elif to == S.CANCELLED and was_paid:
        notify(order, Event.CANCELLED)
    return order


@transaction.atomic
def mark_refunded(order: Order, *, by=None, note: str = "") -> Order:
    """The owner refunded a cancelled order in the bank's merchant portal (MVP: manual)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != S.CANCELLED or order.payment_status != Order.PaymentStatus.PAID:
        raise InvalidTransition("only a paid, cancelled order can be marked refunded")
    order.payment_status = Order.PaymentStatus.REFUNDED
    order.save()
    history(order, order.status, note=note.strip() or _("Refunded"), by=by)
    return order


@transaction.atomic
def resolve_attention(order: Order, *, by=None, note: str = "") -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.needs_attention:
        return order
    order.needs_attention = False
    order.save()
    history(order, order.status, note=note.strip() or _("Resolved"), by=by)
    return order
