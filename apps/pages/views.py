from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.catalog.models import Category
from apps.catalog.queries import (
    COLLECTION_NEW,
    COLLECTION_SALE,
    ProductFilters,
    filter_products,
    listed_products,
)
from apps.core.models import SiteSettings
from apps.core.seo import Seo, alternates, describe, simple_seo
from apps.promotions.services import applies, running_sales

from .models import HeroSlide


def home(request: HttpRequest) -> HttpResponse:
    """Home page (redesign, docs/design/home-reference.jpeg)."""
    sales = running_sales()
    new_items = list(
        filter_products(listed_products(), ProductFilters(), collection=COLLECTION_NEW)[:4]
    )
    banner_sale = next((sale for sale in sales if sale.show_on_home), None)
    example = None
    if banner_sale is not None:
        # The banner's old -> new price is a real discounted piece, never invented numbers.
        on_sale = filter_products(listed_products(), ProductFilters(), collection=COLLECTION_SALE)
        example = next((p for p in on_sale[:24] if applies(banner_sale, p)), None)
        if example is None:
            banner_sale = None  # nothing in this sale is listed right now
    brand = SiteSettings.load().brand_name
    seo = Seo(
        title=f"{brand} — {_('Handmade jewelry with natural stones')}",
        description=describe(
            SiteSettings.load().intro_text, _("Handmade jewelry with natural stones")
        ),
        canonical=request.build_absolute_uri(reverse("pages:home")),
        alternates=alternates(request, lambda: reverse("pages:home")),
        json_ld=[
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": brand,
                "url": request.build_absolute_uri("/"),
            }
        ],
    )
    return render(
        request,
        "pages/home.html",
        {
            "slides": list(HeroSlide.objects.filter(is_active=True)),
            "tiles": Category.objects.filter(is_active=True, show_on_home=True).order_by(
                "home_order", "pk"
            )[:4],
            "new_items": new_items,
            "banner_sale": banner_sale,
            "example": example,
            "seo": seo,
        },
    )


def about(request: HttpRequest) -> HttpResponse:
    """Placeholder: the owner writes the real story (no invented text, CLAUDE.md)."""
    return render(
        request,
        "pages/about.html",
        {"seo": simple_seo(request, "pages:about", _("About"), noindex=True)},
    )


def contact(request: HttpRequest) -> HttpResponse:
    """Contact details from Site settings; the contact form arrives in Phase 2."""
    return render(
        request, "pages/contact.html", {"seo": simple_seo(request, "pages:contact", _("Contact"))}
    )


def account(request: HttpRequest) -> HttpResponse:
    """Optional customer accounts are Phase 3; checkout never requires one (guest checkout)."""
    return render(
        request,
        "pages/account.html",
        {"seo": simple_seo(request, "pages:account", _("Account"), noindex=True)},
    )
