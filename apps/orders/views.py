from dataclasses import dataclass
from datetime import datetime

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET

from apps.cart.services import get_cart
from apps.core.seo import simple_seo
from apps.payments.services import refresh

from .models import Order

S = Order.Status
CHECKOUT_ORDER_KEY = "checkout_order"  # session: the order this browser is paying for
POLL_EVERY_SECONDS = 3
MAX_POLLS = 20  # ~60 s, then "we'll email you"

STEPS = (
    ("placed", gettext_lazy("Placed")),
    ("paid", gettext_lazy("Paid")),
    (S.PROCESSING, gettext_lazy("Being prepared")),
    (S.SHIPPED, gettext_lazy("Shipped")),
    (S.DELIVERED, gettext_lazy("Delivered")),
)
REACHED = {S.AWAITING_PAYMENT: 0, S.NEW: 1, S.PROCESSING: 2, S.SHIPPED: 3, S.DELIVERED: 4}


@dataclass
class Step:
    label: str
    done: bool
    current: bool
    at: datetime | None


def timeline(order: Order) -> list[Step]:
    reached = REACHED.get(order.status, -1)
    when = {"placed": order.created_at, "paid": order.paid_at}
    for entry in order.history.all():
        when.setdefault(entry.to_status, entry.created_at)
    return [
        Step(label=str(label), done=i <= reached, current=i == reached, at=when.get(key))
        for i, (key, label) in enumerate(STEPS)
    ]


@require_GET
def detail(request: HttpRequest, token) -> HttpResponse:
    """The customer's order page (no login; the link is in their email)."""
    order = get_object_or_404(Order, public_token=token)
    order = refresh(order)

    # The browser that paid empties its cart once the bank has confirmed.
    cart_cleared = False
    if order.is_paid and request.session.get(CHECKOUT_ORDER_KEY) == str(order.public_token):
        get_cart(request).clear()
        del request.session[CHECKOUT_ORDER_KEY]
        cart_cleared = True

    try:
        poll = int(request.GET.get("poll", 0))
    except ValueError:
        poll = 0
    waiting = order.status == S.AWAITING_PAYMENT
    context = {
        "order": order,
        "items": order.items.all(),
        "steps": timeline(order),
        "polling": waiting and poll < MAX_POLLS,
        "gave_up_waiting": waiting and poll >= MAX_POLLS,
        "next_poll": poll + 1,
        "poll_every": POLL_EVERY_SECONDS,
        "cart_cleared": cart_cleared,
        "seo": simple_seo(
            request,
            "orders:detail",
            _("Order %(number)s") % {"number": order.number},
            noindex=True,
            token=order.public_token,
        ),
    }
    template = "orders/_detail_partial.html" if request.htmx else "orders/detail.html"
    response = render(request, template, context)
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"  # the token never leaks to other sites
    return response
