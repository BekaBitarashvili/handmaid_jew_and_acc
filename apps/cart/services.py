"""Session cart (SPEC §5 cart, §6.3). No model: the session holds what the customer chose,
the database decides everything else.

Session format (key `cart`):
    {"lines": {"<variant id>": {"qty": 2, "seen": 8400, "gone": false}}, "gift_wrap": false}

- `seen` is the unit price (tetri) the customer last saw. Prices are always recomputed
  through the pricing service; when the new price differs, the customer is told once and
  `seen` is updated.
- `gone` marks a line whose piece was sold or went out of stock. It stays visible in a
  "no longer available" block (never removed silently) until the customer removes it.

Adding to the cart reserves nothing: stock is held only at checkout (SPEC §7).
"""

from dataclasses import dataclass, field
from enum import StrEnum

from django.db.models import Prefetch
from django.utils.translation import gettext as _

from apps.catalog.models import Product, ProductImage, ProductVariant
from apps.core.models import SiteSettings
from apps.core.money import format_gel
from apps.orders.models import DeliveryOption
from apps.promotions.services import PriceInfo, price_for, running_sales

SESSION_KEY = "cart"
MAX_QTY = 10  # per line, for pieces made in several copies
MAX_LINES = 30


class AddResult(StrEnum):
    ADDED = "added"
    ALREADY = "already"  # one-of-a-kind piece already in the cart
    LIMIT = "limit"  # quantity already at its cap
    UNAVAILABLE = "unavailable"
    FULL = "full"


ADD_MESSAGES = {
    AddResult.ADDED: lambda: _("Added to your cart."),
    AddResult.ALREADY: lambda: _("This piece is already in your cart — there is only one."),
    AddResult.LIMIT: lambda: _("You already have all available pieces in your cart."),
    AddResult.UNAVAILABLE: lambda: _("Sorry — this piece is no longer available."),
    AddResult.FULL: lambda: _("Your cart is full. Remove something to add more."),
}


def line_cap(variant: ProductVariant) -> int:
    """How many of this variant one line may hold."""
    if variant.product.is_unique:
        return min(1, max(variant.available, 0))
    return max(min(variant.available, MAX_QTY), 0)


def is_sellable(variant: ProductVariant) -> bool:
    return variant.product.status == Product.Status.ACTIVE and variant.available > 0


# --- Built cart (what templates and checkout read) -------------------------------------


@dataclass
class CartLine:
    variant: ProductVariant
    qty: int
    price: PriceInfo  # unit price

    @property
    def product(self) -> Product:
        return self.variant.product

    @property
    def total(self) -> int:
        return self.price.current * self.qty

    @property
    def original_total(self) -> int:
        return self.price.original * self.qty

    @property
    def savings(self) -> int:
        return self.original_total - self.total

    @property
    def cap(self) -> int:
        return line_cap(self.variant)

    @property
    def show_variant_name(self) -> bool:
        return bool(self.variant.name)

    @property
    def image(self) -> ProductImage | None:
        images = list(self.product.images.all())
        own = next((i for i in images if i.variant_id == self.variant.pk), None)
        return own or (images[0] if images else None)


@dataclass
class GoneLine:
    """A line whose piece can't be bought any more; shown until the customer removes it."""

    variant: ProductVariant
    reason: str

    @property
    def product(self) -> Product:
        return self.variant.product

    @property
    def image(self) -> ProductImage | None:
        images = list(self.product.images.all())
        return images[0] if images else None


@dataclass
class ShippingEstimate:
    """Before checkout the address is unknown: "Delivery from X ₾" + pickup (SPEC §6.3)."""

    delivery_from: int | None  # cheapest active option that needs an address
    pickup: int | None  # price of the first active pickup option
    threshold: int | None  # free-shipping threshold (items after sales, no gift wrap)
    free: bool  # threshold reached
    remaining: int  # tetri still missing for free delivery (0 when reached / no threshold)
    progress: int  # 0..100 for the hint bar


@dataclass
class Cart:
    lines: list[CartLine] = field(default_factory=list)
    gone: list[GoneLine] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    gift_wrap: bool = False
    gift_wrap_price: int = 0  # the configured price, whether chosen or not
    shipping: ShippingEstimate | None = None

    @property
    def count(self) -> int:
        return sum(line.qty for line in self.lines)

    @property
    def is_empty(self) -> bool:
        return not self.lines and not self.gone

    @property
    def subtotal(self) -> int:
        """What the pieces cost after sales; the free-shipping threshold is measured on this."""
        return sum(line.total for line in self.lines)

    @property
    def savings(self) -> int:
        return sum(line.savings for line in self.lines)

    @property
    def gift_wrap_total(self) -> int:
        return self.gift_wrap_price if self.gift_wrap and self.lines else 0

    @property
    def total(self) -> int:
        """Items + gift wrap. Delivery is added at checkout, once the address is known."""
        return self.subtotal + self.gift_wrap_total


def shipping_estimate(subtotal: int, site: SiteSettings | None = None) -> ShippingEstimate:
    site = site or SiteSettings.load()
    threshold = site.free_shipping_threshold
    free = threshold is not None and subtotal >= threshold
    options = list(DeliveryOption.objects.filter(is_active=True))

    def cost(option: DeliveryOption) -> int:
        return 0 if free and option.free_over_threshold else option.price

    address = [cost(o) for o in options if o.requires_address]
    pickup = next((cost(o) for o in options if not o.requires_address), None)
    remaining = max(threshold - subtotal, 0) if threshold is not None else 0
    progress = 100 if free or not threshold else min(subtotal * 100 // threshold, 99)
    return ShippingEstimate(
        delivery_from=min(address) if address else None,
        pickup=pickup,
        threshold=threshold,
        free=free,
        remaining=remaining,
        progress=progress,
    )


# --- Session cart ------------------------------------------------------------------------


class SessionCart:
    def __init__(self, session):
        self.session = session
        data = session.get(SESSION_KEY) or {}
        self.lines: dict[str, dict] = dict(data.get("lines") or {})
        self.gift_wrap: bool = bool(data.get("gift_wrap"))

    # Cheap reads (no queries): header count and "in cart" states.
    @property
    def count(self) -> int:
        return sum(int(line["qty"]) for line in self.lines.values() if not line.get("gone"))

    @property
    def variant_ids(self) -> set[int]:
        return {int(pk) for pk, line in self.lines.items() if not line.get("gone")}

    def qty_of(self, variant_id: int) -> int:
        line = self.lines.get(str(variant_id))
        return int(line["qty"]) if line and not line.get("gone") else 0

    def save(self) -> None:
        self.session[SESSION_KEY] = {"lines": self.lines, "gift_wrap": self.gift_wrap}
        self.session.modified = True

    # Changes.
    def add(self, variant: ProductVariant, qty: int = 1) -> AddResult:
        key = str(variant.pk)
        if not is_sellable(variant):
            return AddResult.UNAVAILABLE
        current = self.qty_of(variant.pk)
        cap = line_cap(variant)
        if current >= cap:
            return AddResult.ALREADY if variant.product.is_unique else AddResult.LIMIT
        if key not in self.lines and len(self.lines) >= MAX_LINES:
            return AddResult.FULL
        sales = running_sales()
        self.lines[key] = {
            "qty": min(current + max(qty, 1), cap),
            "seen": price_for(variant.product, variant.price, sales).current,
        }
        self.save()
        return AddResult.ADDED

    def set_qty(self, variant: ProductVariant, qty: int) -> int:
        """Set a line's quantity within its cap; 0 or less removes it. Returns the new qty."""
        key = str(variant.pk)
        if key not in self.lines:
            return 0
        if qty <= 0:
            self.remove(variant.pk)
            return 0
        qty = min(qty, line_cap(variant))
        if qty <= 0:
            return 0  # sold out meanwhile: build() moves it to the gone block
        self.lines[key]["qty"] = qty
        self.save()
        return qty

    def remove(self, variant_id: int) -> None:
        if self.lines.pop(str(variant_id), None) is not None:
            self.save()

    def set_gift_wrap(self, value: bool) -> None:
        self.gift_wrap = bool(value)
        self.save()

    def clear(self) -> None:
        self.lines = {}
        self.gift_wrap = False
        self.save()

    # Full cart with fresh prices and the "never silent" checks.
    def build(self) -> Cart:
        site = SiteSettings.load()
        cart = Cart(gift_wrap=self.gift_wrap, gift_wrap_price=site.gift_wrap_price)
        ids = [int(pk) for pk in self.lines]
        variants = {
            v.pk: v
            for v in ProductVariant.objects.filter(pk__in=ids)
            .select_related("product__category")
            .prefetch_related(
                Prefetch(
                    "product__images", queryset=ProductImage.objects.order_by("sort_order", "pk")
                )
            )
        }
        sales = running_sales() if variants else []
        changed = False

        for key, data in list(self.lines.items()):
            variant = variants.get(int(key))
            if variant is None:
                del self.lines[key]
                cart.notices.append(_("A piece in your cart is no longer available."))
                changed = True
                continue
            product = variant.product
            name = product.name

            if not is_sellable(variant):
                if product.status == Product.Status.SOLD:
                    reason = _("Sold")
                    notice = _("%(name)s has just been sold.")
                elif product.status == Product.Status.ACTIVE:
                    reason = _("Out of stock")
                    notice = _("%(name)s is out of stock right now.")
                else:
                    reason = _("No longer available")
                    notice = _("%(name)s is no longer available.")
                cart.gone.append(GoneLine(variant=variant, reason=reason))
                if not data.get("gone"):
                    data["gone"] = True
                    cart.notices.append(notice % {"name": name})
                    changed = True
                continue
            if data.get("gone"):  # back in stock: quietly return to the cart
                data.pop("gone")
                changed = True

            qty, cap = int(data["qty"]), line_cap(variant)
            if qty > cap:
                data["qty"] = qty = cap
                cart.notices.append(
                    _("Only %(n)s of %(name)s left — quantity changed to %(n)s.")
                    % {"n": cap, "name": name}
                )
                changed = True

            price = price_for(product, variant.price, sales)
            seen = data.get("seen")
            if seen is not None and seen != price.current:
                cart.notices.append(
                    _("The price of %(name)s changed from %(old)s to %(new)s.")
                    % {"name": name, "old": format_gel(seen), "new": format_gel(price.current)}
                )
            if seen != price.current:
                data["seen"] = price.current
                changed = True
            cart.lines.append(CartLine(variant=variant, qty=qty, price=price))

        if changed:
            self.save()
        cart.shipping = shipping_estimate(cart.subtotal, site)
        return cart


def get_cart(request) -> SessionCart:
    """One SessionCart per request (views and the context processor share it)."""
    if not hasattr(request, "_session_cart"):
        request._session_cart = SessionCart(request.session)
    return request._session_cart
