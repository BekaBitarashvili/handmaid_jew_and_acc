from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.models import SiteSettings
from apps.core.seo import Seo, alternates, describe


def _simple_seo(request: HttpRequest, name: str, title: str, *, noindex: bool = False) -> Seo:
    brand = SiteSettings.load().brand_name
    return Seo(
        title=f"{title} | {brand}",
        description=describe(_("Handmade jewelry with natural stones")),
        canonical=request.build_absolute_uri(reverse(name)),
        alternates=alternates(request, lambda: reverse(name)),
        noindex=noindex,
    )


def home(request: HttpRequest) -> HttpResponse:
    # Replaced by the editorial home page in the next redesign step.
    return render(request, "pages/home.html")


def about(request: HttpRequest) -> HttpResponse:
    """Placeholder: the owner writes the real story (no invented text, CLAUDE.md)."""
    return render(
        request,
        "pages/about.html",
        {"seo": _simple_seo(request, "pages:about", _("About"), noindex=True)},
    )


def contact(request: HttpRequest) -> HttpResponse:
    """Contact details from Site settings; the contact form arrives in Phase 2."""
    return render(
        request, "pages/contact.html", {"seo": _simple_seo(request, "pages:contact", _("Contact"))}
    )


def account(request: HttpRequest) -> HttpResponse:
    """Optional customer accounts are Phase 3; checkout never requires one (guest checkout)."""
    return render(
        request,
        "pages/account.html",
        {"seo": _simple_seo(request, "pages:account", _("Account"), noindex=True)},
    )
