"""Wishlist without accounts (SPEC §5 wishlist): product IDs in a signed cookie, newest first.

The cookie holds no personal data and exists only after the customer presses the heart, so
it counts as strictly necessary (no consent banner needed for it). Tampered cookies are
ignored. A read-only share link carries the IDs in a signed token.
"""

from django.conf import settings
from django.core import signing
from django.http import HttpRequest, HttpResponse

from apps.catalog.models import Product
from apps.catalog.queries import public_products, with_card_data

COOKIE_NAME = "wishlist"
SALT = "wishlist.v1"
SHARE_SALT = "wishlist.share.v1"
MAX_ITEMS = 50
MAX_AGE = 365 * 24 * 60 * 60  # one year


def parse(raw: str) -> list[int]:
    ids: list[int] = []
    for part in (raw or "").split(","):
        if part.isdigit() and int(part) not in ids:
            ids.append(int(part))
    return ids[:MAX_ITEMS]


def read_ids(request: HttpRequest) -> list[int]:
    """IDs from the cookie (cached per request; updated by `remember`)."""
    if not hasattr(request, "_wishlist_ids"):
        raw = request.get_signed_cookie(COOKIE_NAME, default="", salt=SALT)
        request._wishlist_ids = parse(raw)
    return request._wishlist_ids


def remember(request: HttpRequest, response: HttpResponse, ids: list[int]) -> None:
    """Write the cookie, and let the rest of this request (counts, hearts) see the new list."""
    ids = ids[:MAX_ITEMS]
    request._wishlist_ids = ids
    response.set_signed_cookie(
        COOKIE_NAME,
        ",".join(map(str, ids)),
        salt=SALT,
        max_age=MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )


def toggled(ids: list[int], product_id: int) -> tuple[list[int], bool]:
    """New list and whether the piece is now saved. New pieces go first; past the limit the
    oldest one drops off."""
    if product_id in ids:
        return [pk for pk in ids if pk != product_id], False
    return [product_id, *ids][:MAX_ITEMS], True


def products_for(ids: list[int]) -> list[Product]:
    """Saved pieces a visitor may still open (active or sold), in the saved order. Hidden,
    draft and deleted pieces drop out."""
    found = {p.pk: p for p in with_card_data(public_products()).filter(pk__in=ids)}
    return [found[pk] for pk in ids if pk in found]


def share_token(ids: list[int]) -> str:
    return signing.dumps(ids, salt=SHARE_SALT, compress=True)


def ids_from_token(token: str) -> list[int] | None:
    try:
        data = signing.loads(token, salt=SHARE_SALT)
    except signing.BadSignature:
        return None
    if not isinstance(data, list) or not all(isinstance(pk, int) for pk in data):
        return None
    return data[:MAX_ITEMS]
