"""Order events → emails, sent by huey after the transaction commits (never for a change
that was rolled back, and never more than once per event)."""

from enum import StrEnum

from django.db import transaction


class Event(StrEnum):
    PAID = "paid"  # customer confirmation + owner "new order"
    ATTENTION = "attention"  # owner: something needs a manual decision (e.g. refund)
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"  # paid order cancelled by the owner


def notify(order, event: Event) -> None:
    from .tasks import send_order_emails

    order_id = order.pk
    transaction.on_commit(lambda: send_order_emails(order_id, str(event)))
