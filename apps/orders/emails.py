"""Order emails (SPEC §6.7): HTML in the shop's look + plain text, in the order's language
for the customer and in the admin language (Georgian) for the owner."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import translation
from django.utils.translation import gettext as _

from apps.catalog.models import Product
from apps.core.models import SiteSettings

from .models import Order
from .notifications import Event

logger = logging.getLogger(__name__)


def absolute(path: str) -> str:
    if not path or path.startswith(("http://", "https://")):
        return path
    return f"{settings.SITE_URL}{path}"


def _admin_url(order: Order) -> str:
    try:
        return absolute(reverse("admin:orders_order_change", args=[order.pk]))
    except NoReverseMatch:
        return ""


def _care_tips(order: Order) -> list[tuple[str, str]]:
    """(product name, care text) for the delivered email, in the active language."""
    product_ids = order.items.values_list("variant__product_id", flat=True)
    tips = []
    for product in Product.objects.filter(pk__in=set(product_ids)):
        if product.care_instructions:
            tips.append((product.name, product.care_instructions))
    return tips


def _send(template: str, subject: str, to: str, context: dict, reply_to: str = "") -> int:
    html = render_to_string(f"emails/{template}.html", context)
    text = render_to_string(f"emails/{template}.txt", context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
        reply_to=[reply_to] if reply_to else None,
    )
    message.attach_alternative(html, "text/html")
    return message.send()


def _context(order: Order, site: SiteSettings, language: str) -> dict:
    with translation.override(order.language):
        order_url = absolute(order.get_absolute_url())
    return {
        "order": order,
        "items": [(item, absolute(item.image_url)) for item in order.items.all()],
        "site": site,
        "brand": site.brand_name,
        "order_url": order_url,
        "admin_url": _admin_url(order),
        "home_url": absolute(f"/{language}/"),
        "italic": language != "ka",  # Georgian has no italic (SPEC §9.3)
        "language": language,
    }


CUSTOMER = {
    Event.PAID: ("confirmation", lambda o: _("Thank you for your order %(number)s")),
    Event.SHIPPED: ("shipped", lambda o: _("Your order %(number)s is on its way")),
    Event.DELIVERED: ("delivered", lambda o: _("Your order %(number)s has arrived")),
    Event.CANCELLED: ("cancelled", lambda o: _("Your order %(number)s was cancelled")),
}
OWNER = {
    Event.PAID: ("owner_new_order", lambda o: _("New order %(number)s — %(total)s")),
    Event.ATTENTION: ("owner_attention", lambda o: _("Needs attention: order %(number)s")),
    Event.CANCELLED: ("owner_cancelled", lambda o: _("Order %(number)s cancelled")),
}


def send_for_event(order: Order, event: str) -> int:
    from apps.core.money import format_gel

    site = SiteSettings.load()
    sent = 0
    event = Event(event)

    if event in CUSTOMER:
        template, subject = CUSTOMER[event]
        with translation.override(order.language):
            context = _context(order, site, order.language)
            if event == Event.DELIVERED:
                context["care_tips"] = _care_tips(order)
            title = subject(order) % {"number": order.number}
            sent += _send(template, title, order.email, context, reply_to=site.contact_email)

    owner_email = site.owner_notification_email or site.contact_email
    if event in OWNER:
        if not owner_email:
            logger.warning("no owner email in Site settings; %s for %s not sent", event, order)
        else:
            template, subject = OWNER[event]
            language = settings.LANGUAGE_CODE
            with translation.override(language):
                context = _context(order, site, language)
                title = subject(order) % {"number": order.number, "total": format_gel(order.total)}
                sent += _send(template, title, owner_email, context, reply_to=order.email)
    return sent
