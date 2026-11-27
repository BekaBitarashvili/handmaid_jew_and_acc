from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Product
from apps.catalog.queries import public_products
from apps.core.seo import simple_seo

from . import services


@require_GET
def wishlist(request: HttpRequest) -> HttpResponse:
    ids = services.read_ids(request)
    products = services.products_for(ids)
    kept = [p.pk for p in products]
    context = {
        "products": products,
        "share_url": request.build_absolute_uri(
            reverse("wishlist:shared", kwargs={"token": services.share_token(kept)})
        )
        if products
        else "",
        "seo": simple_seo(request, "wishlist:list", _("Wishlist"), noindex=True),
    }
    response = render(request, "wishlist/wishlist.html", context)
    if kept != ids:  # hidden or deleted pieces drop out quietly
        services.remember(request, response, kept)
    return response


@require_POST
def toggle(request: HttpRequest, product_id: int) -> HttpResponse:
    ids = services.read_ids(request)
    if product_id not in ids:  # removing always works; saving only for public pieces
        get_object_or_404(public_products(), pk=product_id)
    ids, saved = services.toggled(ids, product_id)
    request._wishlist_ids = ids  # counts and hearts in this response see the change
    view = request.POST.get("view")

    if not request.htmx:
        target = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
            target = "wishlist:list"
        response = redirect(target)
    elif view == "page":
        products = services.products_for(ids)
        response = render(
            request, "wishlist/_grid_partial.html", {"products": products, "oob": True}
        )
    else:
        product = get_object_or_404(Product, pk=product_id)
        response = render(
            request, "wishlist/_heart.html", {"product": product, "saved": saved, "oob": True}
        )
    services.remember(request, response, ids)
    return response


@require_GET
def shared(request: HttpRequest, token: str) -> HttpResponse:
    ids = services.ids_from_token(token)
    if ids is None:
        raise Http404
    return render(
        request,
        "wishlist/shared.html",
        {
            "products": services.products_for(ids),
            "seo": simple_seo(
                request, "wishlist:shared", _("Shared wishlist"), noindex=True, token=token
            ),
        },
    )
