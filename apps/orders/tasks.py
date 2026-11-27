from huey.contrib.djhuey import db_task

from .models import Order


@db_task(retries=3, retry_delay=60)
def send_order_emails(order_id: int, event: str) -> int:
    """Send the emails for one order event (the SMTP server may be briefly unreachable:
    huey retries). Returns the number of messages sent."""
    from .emails import send_for_event

    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return 0
    return send_for_event(order, event)
