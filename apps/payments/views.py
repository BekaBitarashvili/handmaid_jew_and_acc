import logging

from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import translation
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .models import Payment
from .providers import InvalidCallback, fake_enabled, get_provider
from .services import handle_callback, handle_callback_data

logger = logging.getLogger(__name__)


@csrf_exempt  # server-to-server: authenticated by the provider's signature instead
@require_POST
def callback(request: HttpRequest, provider: str) -> HttpResponse:
    try:
        get_provider(provider)
    except LookupError as error:
        raise Http404 from error
    try:
        handle_callback(provider, request)
    except InvalidCallback as error:
        logger.warning(
            "rejected %s callback (%s): %r", provider, error, request.body[:500], exc_info=False
        )
        return HttpResponseBadRequest("invalid callback")
    except Payment.DoesNotExist as error:
        raise Http404 from error
    return HttpResponse("ok")


@require_http_methods(["GET", "POST"])
def fake_bank(request: HttpRequest, reference: str) -> HttpResponse:
    """The fake provider's "hosted payment page" (dev and tests only)."""
    if not fake_enabled():
        raise Http404
    payment = get_object_or_404(
        Payment.objects.select_related("order"), provider="fake", provider_order_id=reference
    )
    order = payment.order
    if request.method == "POST":
        decision = request.POST.get("decision")
        if decision not in ("paid", "failed", "delay"):
            return HttpResponseBadRequest("unknown decision")
        provider = get_provider("fake")
        body = provider.decide(payment, decision)
        if body is not None:  # the "bank" calls back before sending the customer home
            handle_callback_data("fake", provider.verify_body(body))
        with translation.override(order.language):
            return redirect(order.get_absolute_url())
    return render(request, "payments/fake_bank.html", {"payment": payment, "order": order})
