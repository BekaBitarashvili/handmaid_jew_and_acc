from django import template

from apps.core.money import format_gel

register = template.Library()


@register.filter
def gel(tetri: int | None) -> str:
    """{{ product.price|gel }} -> "145 ₾"."""
    if tetri is None or tetri == "":
        return ""
    return format_gel(int(tetri))
