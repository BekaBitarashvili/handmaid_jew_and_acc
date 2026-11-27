from django.http import HttpRequest

from .services import get_cart


def cart(request: HttpRequest) -> dict:
    """Header count and "in cart" states, read from the session only (no queries, and the
    cart's one-time notices are left for the drawer or cart page to show)."""
    session_cart = get_cart(request)
    return {"cart_count": session_cart.count, "cart_variant_ids": session_cart.variant_ids}
