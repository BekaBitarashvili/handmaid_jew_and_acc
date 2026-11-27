"""Checkout (SPEC §6.4): one page, guest only. The summary follows the delivery and gift
choices through HTMX; placing the order is a plain POST that ends on the bank's page."""

import uuid

from django.contrib import messages
from django.core.cache import cache
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from apps.cart.services import delivery_price, get_cart
from apps.core.models import SiteSettings
from apps.core.seo import simple_seo
from apps.payments.providers import fake_enabled
from apps.payments.services import expire_overdue, start_payment, sync_status

from .forms import GIFT_NOTE_MAX, CheckoutForm
from .models import DeliveryOption, Order
from .services import CheckoutError, EmptyCart, fail_payment, place_order, quote
from .views import CHECKOUT_ORDER_KEY

TOKEN_KEY = "checkout_token"
RATE_LIMIT = 10  # orders per IP ...
RATE_WINDOW = 10 * 60  # ... per 10 minutes


def _client_ip(request: HttpRequest) -> str | None:
    return request.META.get("REMOTE_ADDR") or None


def _rate_limited(request: HttpRequest) -> bool:
    key = f"checkout-rate:{_client_ip(request)}"
    cache.add(key, 0, RATE_WINDOW)
    try:
        return cache.incr(key) > RATE_LIMIT
    except ValueError:  # the key expired in between (or a dummy cache): don't block
        return False


def _token(request: HttpRequest) -> str:
    if TOKEN_KEY not in request.session:
        request.session[TOKEN_KEY] = uuid.uuid4().hex
    return request.session[TOKEN_KEY]


def close_unpaid_checkout(request: HttpRequest) -> bool:
    """Back from the bank page to the cart or checkout: this browser's unpaid order is
    abandoned, so its pieces are released (they show as available again, not as taken by
    someone else). If the customer still pays in the bank's tab, the late payment is
    accepted while the pieces are free."""
    token = request.session.get(CHECKOUT_ORDER_KEY)
    if not token:
        return False
    order = Order.objects.filter(public_token=token, status=Order.Status.AWAITING_PAYMENT).first()
    if order is None:
        return False
    if sync_status(order).status != Order.Status.AWAITING_PAYMENT:  # the bank had an answer
        return False
    fail_payment(order.pk, replaced=True)
    return True


def _option(raw) -> DeliveryOption | None:
    options = DeliveryOption.objects.filter(is_active=True)
    try:
        return options.get(pk=int(raw))
    except (TypeError, ValueError, DeliveryOption.DoesNotExist):
        return options.first()


def summary_context(request: HttpRequest, option: DeliveryOption | None, gift_wrap: bool):
    session_cart = get_cart(request)
    if session_cart.gift_wrap != gift_wrap:
        session_cart.set_gift_wrap(gift_wrap)
    cart = session_cart.build()
    site = SiteSettings.load()
    return {
        "cart": cart,
        "quote": quote(cart, option, site),
        "option": option,
        "options": [
            (o, delivery_price(o, cart.subtotal, site))
            for o in DeliveryOption.objects.filter(is_active=True)
        ],
        "summary_notices": cart.notices,
    }


def _render(request, form, *, notices=(), status=200):
    option = _option(form["delivery"].value())
    gift = form["gift_wrap"].value() in (True, "on", "true", "1")
    context = summary_context(request, option, gift)
    context.update(
        {
            "form": form,
            "notices": [*notices, *context.pop("summary_notices")],
            "gift_note_max": GIFT_NOTE_MAX,
            "test_mode": fake_enabled(),
            "seo": simple_seo(request, "orders:checkout", _("Checkout"), noindex=True),
        }
    )
    if not context["cart"].lines:
        for notice in context["notices"]:  # never silent, also across the redirect
            messages.info(request, notice)
        return redirect("cart:detail")
    return render(request, "orders/checkout.html", context, status=status)


@require_http_methods(["GET", "POST"])
def checkout(request: HttpRequest) -> HttpResponse:
    expire_overdue()  # frees pieces held by abandoned checkouts (also run by huey)
    session_cart = get_cart(request)

    if request.method == "GET":
        close_unpaid_checkout(request)
        if not session_cart.count:
            return redirect("cart:detail")
        form = CheckoutForm(
            initial={
                "gift_wrap": session_cart.gift_wrap,
                "delivery": DeliveryOption.objects.filter(is_active=True).first(),
                "checkout_token": _token(request),
            }
        )
        return _render(request, form)

    form = CheckoutForm(request.POST)
    if not form.is_valid():
        return _render(request, form, status=200)

    data = form.to_checkout_data()
    # Double submit: this form already became an order -> carry on with that one.
    existing = Order.objects.filter(checkout_token=data.checkout_token).first()
    if existing:
        return redirect(existing.get_absolute_url())
    if _rate_limited(request):
        return _render(
            request, form, notices=[_("Too many attempts. Please wait a few minutes.")], status=429
        )

    # A new checkout closes this browser's earlier unpaid order (and frees its pieces).
    close_unpaid_checkout(request)

    try:
        order = place_order(
            session_cart,
            data,
            language=get_language() or "ka",
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except EmptyCart:
        return redirect("cart:detail")
    except CheckoutError as error:
        return _render(request, form, notices=error.messages)
    except IntegrityError:  # the same form was submitted twice at the same moment
        existing = Order.objects.filter(checkout_token=data.checkout_token).first()
        if existing:
            return redirect(existing.get_absolute_url())
        raise

    request.session[CHECKOUT_ORDER_KEY] = str(order.public_token)
    request.session[TOKEN_KEY] = uuid.uuid4().hex  # the next checkout gets a new token
    try:
        return redirect(start_payment(order, request))
    except Exception:
        fail_payment(order.pk)
        messages.error(request, _("The payment could not be started. Please try again."))
        return redirect("orders:checkout")


@require_GET
def checkout_summary(request: HttpRequest) -> HttpResponse:
    """HTMX: the summary after a delivery or gift wrap change."""
    option = _option(request.GET.get("delivery"))
    context = summary_context(request, option, request.GET.get("gift_wrap") == "on")
    context["notices"] = context.pop("summary_notices")
    return render(request, "orders/_checkout_summary.html", {**context, "oob": True})
