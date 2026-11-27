"""Cart endpoints (SPEC §6.3). HTMX requests get the drawer or page partial back, plus an
out-of-band header count; without JavaScript the same forms post and redirect to /cart/."""

import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import ProductVariant
from apps.core.seo import simple_seo

from .services import ADD_MESSAGES, AddResult, get_cart

DRAWER, PAGE = "drawer", "page"
TEMPLATES = {DRAWER: "cart/_drawer_partial.html", PAGE: "cart/_page_partial.html"}


def _variant(pk) -> ProductVariant:
    return get_object_or_404(ProductVariant.objects.select_related("product__category"), pk=pk)


def _view(request: HttpRequest) -> str:
    return PAGE if request.POST.get("view") == PAGE else DRAWER


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _respond(
    request: HttpRequest,
    view: str,
    message: str = "",
    *,
    triggers: dict | None = None,
    card_variant: ProductVariant | None = None,
) -> HttpResponse:
    if not request.htmx:
        if message:
            messages.info(request, message)
        return redirect("cart:detail")
    cart = get_cart(request).build()
    notices = ([message] if message else []) + cart.notices
    context = {"cart": cart, "notices": notices, "oob": True, "card_variant": card_variant}
    response = render(request, TEMPLATES[view], context)
    if triggers:
        response["HX-Trigger"] = json.dumps(triggers)
    return response


@require_GET
def detail(request: HttpRequest) -> HttpResponse:
    from apps.orders.checkout_views import close_unpaid_checkout

    close_unpaid_checkout(request)  # back from the bank page: release this browser's hold
    cart = get_cart(request).build()
    notices = [str(m) for m in messages.get_messages(request)] + cart.notices
    return render(
        request,
        "cart/cart.html",
        {
            "cart": cart,
            "notices": notices,
            "seo": simple_seo(request, "cart:detail", _("Your cart"), noindex=True),
        },
    )


@require_GET
def drawer(request: HttpRequest) -> HttpResponse:
    return _respond(request, DRAWER)


@require_POST
def add(request: HttpRequest) -> HttpResponse:
    variant = _variant(_int(request.POST.get("variant"), 0))
    result = get_cart(request).add(variant, qty=max(_int(request.POST.get("qty"), 1), 1))
    triggers = {"cart-open": True}
    if result in (AddResult.ADDED, AddResult.ALREADY, AddResult.LIMIT):
        triggers["cart-added"] = {"variant": variant.pk}
    from_card = request.POST.get("source") == "card"
    return _respond(
        request,
        DRAWER,
        ADD_MESSAGES[result](),
        triggers=triggers,
        card_variant=variant if from_card else None,
    )


@require_POST
def update(request: HttpRequest, variant_id: int) -> HttpResponse:
    variant = _variant(variant_id)
    wanted = _int(request.POST.get("qty"), 1)
    got = get_cart(request).set_qty(variant, wanted)
    message = ""
    if 0 < got < wanted:
        message = _("Only %(n)s available.") % {"n": got}
    return _respond(request, _view(request), message)


@require_POST
def remove(request: HttpRequest, variant_id: int) -> HttpResponse:
    variant = ProductVariant.objects.select_related("product").filter(pk=variant_id).first()
    get_cart(request).remove(variant_id)
    message = (
        _("%(name)s was removed from your cart.") % {"name": variant.product.name}
        if variant
        else ""
    )
    return _respond(request, _view(request), message)


@require_POST
def gift_wrap(request: HttpRequest) -> HttpResponse:
    get_cart(request).set_gift_wrap(request.POST.get("gift_wrap") == "1")
    return _respond(request, PAGE)
