from django.http import HttpRequest
from django.utils.functional import SimpleLazyObject

from apps.catalog.queries import public_products

from .services import read_ids


def wishlist(request: HttpRequest) -> dict:
    """Saved IDs (hearts) and the count shown as "Wishlist (n)" — only pieces a visitor may
    still open are counted; the query runs only if a template shows the count."""
    ids = read_ids(request)
    return {
        "wishlist_ids": set(ids),
        "wishlist_count": SimpleLazyObject(
            lambda: public_products().filter(pk__in=ids).count() if ids else 0
        ),
    }
