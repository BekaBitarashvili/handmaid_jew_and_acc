from django.db import transaction
from django.utils import timezone

from .models import OrderNumberSequence


def next_order_number() -> str:
    """26-1001, 26-1002, … — two-digit year and a counter that restarts at 1001 each year.

    The counter row is locked, so two orders placed at once never share a number.
    """
    year = timezone.localdate().year
    with transaction.atomic():
        OrderNumberSequence.objects.get_or_create(year=year)
        sequence = OrderNumberSequence.objects.select_for_update().get(year=year)
        sequence.last_number += 1
        sequence.save(update_fields=["last_number"])
    return f"{year % 100:02d}-{sequence.last_number}"
