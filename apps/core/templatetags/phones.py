from django import template

from apps.core.phones import format_phone

register = template.Library()


@register.filter
def phone(e164: str) -> str:
    """{{ order.phone|phone }} -> "+995 555 12 34 56"."""
    return format_phone(e164 or "")


@register.filter
def tel(e164: str) -> str:
    """{{ order.phone|tel }} -> "tel:+995555123456" (tap-to-call)."""
    return f"tel:{e164}" if e164 else ""
