"""Navigation helpers that only show links whose views exist yet.

Phase 1/2 add the shop, archive, stones and about pages; the header picks them
up automatically once their URL names resolve, without template edits.
"""

from dataclasses import dataclass

from django import template
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

register = template.Library()

MAIN_NAV = (
    ("catalog:shop", _("Shop")),
    ("catalog:archive", _("Archive")),
    ("pages:stones", _("Stones")),
    ("pages:about", _("About")),
)


@dataclass(frozen=True)
class NavItem:
    label: str
    url: str
    active: bool


def _reverse_or_none(name: str) -> str | None:
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


@register.simple_tag(takes_context=True)
def main_nav(context) -> list[NavItem]:
    request = context.get("request")
    path = request.path if request else ""
    items = []
    for name, label in MAIN_NAV:
        if url := _reverse_or_none(name):
            items.append(NavItem(label=str(label), url=url, active=path.startswith(url)))
    return items


@register.simple_tag
def url_if_exists(name: str) -> str:
    """`{% url_if_exists "cart:detail" as cart_url %}` -> "" when the view doesn't exist yet."""
    return _reverse_or_none(name) or ""
