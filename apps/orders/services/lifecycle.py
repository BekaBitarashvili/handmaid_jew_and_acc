"""Payment outcomes (SPEC §6.5). Every function is idempotent: a repeated callback, a poll
and the expiry task may all report the same payment, and only the first one changes
anything. The order row is locked while deciding."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.catalog.services import inventory

from ..models import Order, OrderStatusHistory
from ..notifications import Event, notify


def lines(order: Order) -> list[tuple[int, int]]:
    return [(item.variant_id, item.qty) for item in order.items.all()]


def owner_text(message_factory) -> str:
    """System notes are read by the owner in the admin (Georgian by default)."""
    with translation.override(settings.LANGUAGE_CODE):
        return str(message_factory())


def history(order: Order, from_status: str, note: str = "", by=None) -> None:
    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=order.status, note=note, changed_by=by
    )


def _locked(order_id: int) -> Order:
    return Order.objects.select_for_update().get(pk=order_id)


@transaction.atomic
def confirm_payment(order_id: int) -> Order:
    """The bank says paid. Normally the held pieces leave the stock and the order is new.

    Paid after the hold ended: accepted normally while the pieces are still free;
    if one was sold meanwhile, the order is flagged for the owner to refund.
    """
    order = _locked(order_id)
    if order.payment_status in (Order.PaymentStatus.PAID, Order.PaymentStatus.REFUNDED):
        return order
    previous = order.status
    late = previous != Order.Status.AWAITING_PAYMENT
    try:
        inventory.commit(lines(order), reserved=not late)
    except inventory.OutOfStock as error:
        name = error.product_name or str(error.variant_id)
        order.payment_status = Order.PaymentStatus.PAID
        order.paid_at = timezone.now()
        order.needs_attention = True
        order.attention_reason = owner_text(
            lambda: (
                _(
                    "Paid after the 15-minute hold ended, but %(name)s was sold meanwhile. "
                    "Refund the customer or offer a similar piece."
                )
                % {"name": name}
            )
        )
        order.save()
        history(order, previous, note=order.attention_reason)
        notify(order, Event.ATTENTION)
        return order

    order.status = Order.Status.NEW
    order.payment_status = Order.PaymentStatus.PAID
    order.paid_at = timezone.now()
    order.reservation_expires_at = None
    order.cancel_reason = ""
    order.save()
    note = owner_text(lambda: _("Paid after the hold ended; the pieces were still free."))
    history(order, previous, note=note if late else "")
    notify(order, Event.PAID)
    return order


@transaction.atomic
def fail_payment(order_id: int, *, expired: bool = False, replaced: bool = False) -> Order:
    """Declined, abandoned or expired: the pieces go back, the order is cancelled. A paid or
    already-cancelled order is left alone."""
    order = _locked(order_id)
    if order.status != Order.Status.AWAITING_PAYMENT:
        return order
    inventory.release(lines(order))
    previous = order.status
    order.status = Order.Status.CANCELLED
    order.payment_status = Order.PaymentStatus.FAILED
    order.reservation_expires_at = None
    order.cancel_reason = (
        Order.CancelReason.REPLACED
        if replaced
        else Order.CancelReason.EXPIRED
        if expired
        else Order.CancelReason.PAYMENT_FAILED
    )
    order.save()
    if replaced:
        note = owner_text(lambda: _("The customer started a new checkout."))
    elif expired:
        note = owner_text(lambda: _("Not paid within 15 minutes; the pieces were released."))
    else:
        note = owner_text(lambda: _("The payment did not go through."))
    history(order, previous, note=note)
    return order
