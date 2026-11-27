import pytest

from apps.cart.services import (
    MAX_LINES,
    MAX_QTY,
    AddResult,
    SessionCart,
    shipping_estimate,
)
from apps.catalog.models import Product
from apps.core.models import SiteSettings
from apps.orders.models import DeliveryOption
from apps.promotions.models import Sale
from tests.catalog.factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db
ACTIVE = Product.Status.ACTIVE


class FakeSession(dict):
    modified = False


def unique(price=12000, **kwargs):
    product = ProductFactory(status=ACTIVE, price=price, is_unique=True, **kwargs)
    return product.variants.get()


def multi(stock=3, price=5000, **kwargs):
    product = ProductFactory(status=ACTIVE, price=price, is_unique=False, **kwargs)
    variant = product.variants.get()
    variant.stock = stock
    variant.save()
    return variant


@pytest.fixture
def cart():
    return SessionCart(FakeSession())


def reload(cart):
    """A new request: the same session, a fresh SessionCart."""
    return SessionCart(cart.session)


class TestQuantities:
    def test_unique_piece_is_fixed_at_one(self, cart):
        variant = unique()
        assert cart.add(variant) == AddResult.ADDED
        assert cart.add(variant) == AddResult.ALREADY
        assert cart.set_qty(variant, 5) == 1
        assert cart.count == 1

    def test_unique_stays_one_even_if_stock_says_more(self, cart):
        variant = unique()
        type(variant).objects.filter(pk=variant.pk).update(stock=3)  # bad data, not a reason
        variant.refresh_from_db()
        cart.add(variant, qty=3)
        assert cart.qty_of(variant.pk) == 1

    def test_capped_at_available(self, cart):
        variant = multi(stock=3)
        variant.reserved = 1  # someone else is checking out with one
        variant.save()
        cart.add(variant, qty=5)
        assert cart.qty_of(variant.pk) == 2
        assert cart.add(variant) == AddResult.LIMIT

    def test_capped_at_ten_per_line(self, cart):
        variant = multi(stock=50)
        cart.add(variant, qty=40)
        assert cart.qty_of(variant.pk) == MAX_QTY

    def test_zero_removes(self, cart):
        variant = multi()
        cart.add(variant)
        cart.set_qty(variant, 0)
        assert cart.count == 0 and not cart.lines

    def test_unavailable_pieces_are_refused(self, cart):
        sold = unique()
        sold.product.status = Product.Status.SOLD
        sold.product.save()
        draft = ProductFactory(status=Product.Status.DRAFT).variants.get()
        empty = multi(stock=0)
        assert {cart.add(v) for v in (sold, draft, empty)} == {AddResult.UNAVAILABLE}
        assert cart.count == 0

    def test_line_limit(self, cart):
        for _ in range(MAX_LINES):
            cart.add(unique())
        assert cart.add(unique()) == AddResult.FULL

    def test_unknown_variant_ids_are_dropped_with_a_notice(self, cart):
        cart.session["cart"] = {"lines": {"999999": {"qty": 1, "seen": 100}}}
        built = reload(cart).build()
        assert built.is_empty and len(built.notices) == 1


class TestPricesAndTotals:
    def test_prices_come_from_the_pricing_service(self, cart, en):
        earrings = CategoryFactory()
        variant = unique(price=14550, category=earrings)
        sale = Sale.objects.create(name="s", percent=30)
        sale.categories.set([earrings])
        cart.add(variant)
        cart.add(multi(stock=5, price=5000), qty=2)
        built = cart.build()
        # 30% of 145.50 GEL rounds half up to 43.65 off -> 101.85.
        assert built.lines[0].price.current == 10185
        assert built.subtotal == 10185 + 2 * 5000
        assert built.savings == 4365
        assert built.notices == []  # the price seen when adding is the price now

    def test_gift_wrap_free_and_priced(self, cart):
        cart.add(unique(price=10000))
        cart.set_gift_wrap(True)
        assert cart.build().total == 10000  # default price 0 = free
        site = SiteSettings.load()
        site.gift_wrap_price = 500
        site.save()
        built = reload(cart).build()
        assert (built.gift_wrap_total, built.total) == (500, 10500)

    def test_gift_wrap_costs_nothing_without_pieces(self, cart):
        site = SiteSettings.load()
        site.gift_wrap_price = 500
        site.save()
        cart.set_gift_wrap(True)
        assert cart.build().total == 0


class TestNeverSilent:
    def test_sale_starting_changes_price_once(self, cart, en):
        cart.add(unique(price=10000, name_en="Lapis bracelet"))
        Sale.objects.create(name="s", percent=30, applies_to_all=True)
        first = reload(cart).build()
        assert first.notices == ["The price of Lapis bracelet changed from 100 ₾ to 70 ₾."]
        assert reload(cart).build().notices == []

    def test_sale_ending_changes_price_back(self, cart, en):
        sale = Sale.objects.create(name="s", percent=30, applies_to_all=True)
        cart.add(unique(price=10000, name_en="Ring"))
        sale.is_active = False
        sale.save()
        assert "from 70 ₾ to 100 ₾" in reload(cart).build().notices[0]

    def test_sold_piece_moves_to_gone_block_and_stays(self, cart, en):
        variant = unique(name_en="Amber necklace")
        cart.add(variant)
        variant.product.status = Product.Status.SOLD
        variant.product.save()
        built = reload(cart).build()
        assert built.notices == ["Amber necklace has just been sold."]
        assert built.lines == [] and built.gone[0].reason == "Sold"
        assert built.total == 0 and built.count == 0
        again = reload(cart).build()
        assert again.notices == [] and len(again.gone) == 1  # shown until removed
        reload(cart).remove(variant.pk)
        assert reload(cart).build().is_empty

    def test_out_of_stock_and_back(self, cart, en):
        variant = multi(stock=2)
        cart.add(variant)
        variant.stock = 0
        variant.save()
        assert "out of stock right now" in reload(cart).build().notices[0]
        variant.stock = 2
        variant.save()
        built = reload(cart).build()
        assert built.notices == [] and built.count == 1 and not built.gone

    def test_hidden_piece(self, cart, en):
        variant = unique(name_en="Brooch")
        cart.add(variant)
        variant.product.status = Product.Status.HIDDEN
        variant.product.save()
        assert reload(cart).build().notices == ["Brooch is no longer available."]

    def test_quantity_lowered_to_available(self, cart, en):
        variant = multi(stock=5, name_en="Beaded bracelet")
        cart.add(variant, qty=4)
        variant.stock = 2
        variant.save()
        built = reload(cart).build()
        assert built.notices == ["Only 2 of Beaded bracelet left — quantity changed to 2."]
        assert built.count == 2 and reload(cart).build().notices == []

    def test_count_ignores_gone_lines(self, cart):
        variant = unique()
        cart.add(variant)
        variant.product.status = Product.Status.SOLD
        variant.product.save()
        reload(cart).build()
        assert reload(cart).count == 0 and reload(cart).variant_ids == set()


class TestShippingEstimate:
    @pytest.fixture
    def options(self):
        DeliveryOption.objects.create(code="tbilisi", name="Tbilisi", price=500)
        DeliveryOption.objects.create(code="regions", name="Regions", price=1000)
        DeliveryOption.objects.create(code="far", name="Far", price=1500, free_over_threshold=False)
        DeliveryOption.objects.create(code="pickup", name="Pickup", price=0, requires_address=False)
        DeliveryOption.objects.create(code="off", name="Off", price=100, is_active=False)

    @pytest.fixture
    def threshold(self):
        site = SiteSettings.load()
        site.free_shipping_threshold = 20000
        site.save()

    def test_delivery_from_cheapest_active_address_option(self, options):
        estimate = shipping_estimate(5000)
        assert (estimate.delivery_from, estimate.pickup) == (500, 0)
        assert estimate.threshold is None and estimate.progress == 100

    def test_threshold_below_at_above(self, options, threshold):
        below = shipping_estimate(19999)
        assert not below.free and below.remaining == 1 and below.progress == 99
        at = shipping_estimate(20000)
        assert at.free and at.remaining == 0 and at.delivery_from == 0
        assert shipping_estimate(25000).free

    def test_threshold_uses_items_after_sales_without_gift_wrap(self, cart, options, threshold):
        site = SiteSettings.load()
        site.gift_wrap_price = 5000
        site.save()
        cart.add(unique(price=25000))
        Sale.objects.create(name="s", percent=30, applies_to_all=True)  # 250 -> 175 GEL
        cart.set_gift_wrap(True)
        built = reload(cart).build()
        assert built.total == 22500  # over 200 GEL only because of gift wrap
        assert not built.shipping.free and built.shipping.remaining == 2500

    def test_no_options(self):
        estimate = shipping_estimate(100)
        assert estimate.delivery_from is None and estimate.pickup is None
