import threading
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant
from apps.core.models import SiteSettings
from apps.orders.models import Order, OrderStatusHistory
from apps.orders.services import (
    CartChanged,
    EmptyCart,
    InvalidTransition,
    PieceTaken,
    PricesChanged,
    change_status,
    confirm_payment,
    fail_payment,
    mark_refunded,
    place_order,
    resolve_attention,
)
from apps.promotions.models import Sale

from .helpers import FakeSession, cart_with, courier, data, order_for, pickup, piece

pytestmark = pytest.mark.django_db
S = Order.Status


def stock(variant):
    variant.refresh_from_db()
    return variant.stock, variant.reserved


@pytest.fixture
def owner():
    return get_user_model().objects.create_user("owner", is_staff=True)


class TestPlaceOrder:
    def test_holds_pieces_and_snapshots(self, en):
        variant = piece(price=14550, name_en="Amber necklace")
        order = order_for(variant, option=courier(price=600))
        assert order.status == S.AWAITING_PAYMENT
        assert order.payment_status == Order.PaymentStatus.PENDING
        assert stock(variant) == (1, 1)
        assert order.number.endswith("-1001")
        expires = order.reservation_expires_at - timezone.now()
        assert timedelta(minutes=14) < expires <= timedelta(minutes=15)
        (item,) = order.items.all()
        assert (item.product_name, item.unit_price, item.qty) == ("Amber necklace", 14550, 1)
        assert (order.subtotal, order.shipping_price, order.total) == (14550, 600, 15150)
        assert order.consent_terms and order.consented_at
        assert list(order.history.values_list("to_status", flat=True)) == [S.AWAITING_PAYMENT]

    def test_sale_prices_are_snapshotted(self, en):
        variant = piece(price=10000)
        Sale.objects.create(name="s", percent=30, applies_to_all=True)
        cart = cart_with(variant)
        order = place_order(cart, data(), language="en")
        item = order.items.get()
        assert (item.original_unit_price, item.unit_price, order.savings) == (10000, 7000, 3000)

    def test_free_delivery_over_threshold_and_gift_wrap(self, en):
        site = SiteSettings.load()
        site.free_shipping_threshold = 10000
        site.gift_wrap_price = 500
        site.save()
        order = order_for(piece(price=10000), gift_wrap=True, gift_note="For you")
        assert (order.shipping_price, order.gift_wrap_price, order.total) == (0, 500, 10500)

    def test_pickup_drops_address_and_tbilisi_fixes_city(self, en):
        order = order_for(piece(), option=pickup(), city="Batumi", address_line="x")
        assert (order.city, order.address_line, order.requires_address) == ("", "", False)
        tbilisi = courier(code="courier_tbilisi", name="Courier in Tbilisi")
        order = order_for(piece(), option=tbilisi, city="Batumi")
        assert order.city == "Tbilisi"

    def test_snapshots_in_the_order_language_whatever_is_active(self):
        from django.utils import translation

        variant = piece(name_en="Amber necklace", name_ka="ქარვის ყელსაბამი")
        tbilisi = courier(code="courier_tbilisi", name_en="Courier in Tbilisi", name_ka="კურიერი")
        with translation.override("en"):
            order = place_order(cart_with(variant), data(tbilisi), language="ka")
        assert order.items.get().product_name == "ქარვის ყელსაბამი"
        with translation.override("ka"):
            tbilisi_ka = translation.gettext("Tbilisi")
        assert (order.delivery_name, order.city) == ("კურიერი", tbilisi_ka)

    def test_item_photo_is_a_small_jpeg(self, en):
        from tests.catalog.factories import ProductImageFactory

        variant = piece()
        ProductImageFactory(product=variant.product)
        url = order_for(variant).items.get().image_url
        assert url.endswith(".jpg") and "160x160" in url

    def test_empty_cart(self):
        with pytest.raises(EmptyCart):
            place_order(cart_with(), data(), language="en")

    def test_price_change_between_cart_and_checkout(self, en):
        variant = piece(price=10000, name_en="Ring")
        cart = cart_with(variant)
        Sale.objects.create(name="s", percent=30, applies_to_all=True)  # starts meanwhile
        with pytest.raises(CartChanged) as error:
            place_order(cart, data(), language="en")
        assert "price of Ring changed" in error.value.messages[0]
        assert not Order.objects.exists() and stock(variant) == (1, 0)

    def test_total_seen_must_match(self, en):
        variant = piece(price=10000)
        option = courier(price=600)
        with pytest.raises(PricesChanged):
            place_order(cart_with(variant), data(option, expected_total=10000), language="en")
        order = place_order(cart_with(variant), data(option, expected_total=10600), language="en")
        assert order.total == 10600

    def test_delivery_price_changed_by_owner(self, en):
        option = courier(price=600)
        cart = cart_with(piece(price=10000))
        option.price = 900
        option.save()
        with pytest.raises(PricesChanged):
            place_order(cart, data(option, expected_total=10600), language="en")

    def test_piece_taken_by_someone_else(self, en):
        variant = piece(name_en="Amber necklace")
        first, second = cart_with(variant), cart_with(variant)
        place_order(first, data(), language="en")
        with pytest.raises((PieceTaken, CartChanged)):
            place_order(second, data(), language="en")
        assert Order.objects.count() == 1 and stock(variant) == (1, 1)

    def test_piece_taken_in_the_last_moment(self, en, monkeypatch):
        """Taken between the cart check and the hold: the hold itself refuses."""
        from apps.catalog.services import inventory

        variant = piece(name_en="Amber necklace")
        cart = cart_with(variant)
        real_reserve = inventory.reserve

        def someone_was_faster(lines):
            ProductVariant.objects.filter(pk=variant.pk).update(reserved=1)
            return real_reserve(lines)

        monkeypatch.setattr(inventory, "reserve", someone_was_faster)
        with pytest.raises(PieceTaken) as error:
            place_order(cart, data(), language="en")
        assert error.value.messages == [
            "Someone has just taken Amber necklace. Please check your order."
        ]
        # Nothing was created (the simulated buyer wrote inside the same, rolled-back
        # transaction; the real race is covered by the two-thread test below).
        assert not Order.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_buyers_race_for_one_unique_piece():
    variant = piece(name_en="Last piece")
    option = courier()
    carts = [cart_with(variant), cart_with(variant)]
    barrier = threading.Barrier(2)
    results = []

    def buy(cart):
        try:
            barrier.wait()
            results.append(place_order(cart, data(option), language="en"))
        except (PieceTaken, CartChanged) as error:
            results.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=buy, args=(cart,)) for cart in carts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    orders = [r for r in results if isinstance(r, Order)]
    assert len(orders) == 1 and len(results) == 2
    assert stock(variant) == (1, 1)  # held once, never over-reserved
    assert Order.objects.count() == 1


class TestPayment:
    def test_confirm_commits_stock_and_marks_unique_sold(self, en):
        variant = piece()
        order = confirm_payment(order_for(variant).pk)
        assert (order.status, order.payment_status) == (S.NEW, Order.PaymentStatus.PAID)
        assert order.paid_at and order.reservation_expires_at is None
        assert stock(variant) == (0, 0)
        product = Product.objects.get(pk=variant.product_id)
        assert product.status == Product.Status.SOLD and product.sold_at

    def test_non_unique_at_zero_stays_active(self, en):
        variant = piece(unique=False, stock=2)
        cart = cart_with(variant, qty=2)
        order = place_order(cart, data(), language="en")
        confirm_payment(order.pk)
        assert stock(variant) == (0, 0)
        assert Product.objects.get(pk=variant.product_id).status == Product.Status.ACTIVE

    def test_confirm_is_idempotent(self, en):
        variant = piece(unique=False, stock=3)
        order = order_for(variant)
        confirm_payment(order.pk)
        confirm_payment(order.pk)
        assert stock(variant) == (2, 0)
        assert order.history.count() == 2

    def test_fail_releases_and_ignores_paid(self, en):
        variant = piece()
        order = fail_payment(order_for(variant).pk)
        assert (order.status, order.payment_status) == (S.CANCELLED, Order.PaymentStatus.FAILED)
        assert stock(variant) == (1, 0)
        paid = confirm_payment(order_for(piece()).pk)
        assert fail_payment(paid.pk).status == S.NEW  # a late failure never undoes a payment

    def test_expired_then_paid_while_free_is_accepted(self, en):
        variant = piece()
        order = order_for(variant)
        fail_payment(order.pk, expired=True)
        order = confirm_payment(order.pk)
        assert (order.status, order.needs_attention) == (S.NEW, False)
        assert stock(variant) == (0, 0)
        assert order.history.last().note  # the owner sees why it was accepted late

    def test_expired_then_paid_after_sold_needs_attention(self, en):
        variant = piece(name_en="Amber necklace")
        late = order_for(variant)
        fail_payment(late.pk, expired=True)
        confirm_payment(order_for(variant).pk)  # someone else bought it meanwhile
        late = confirm_payment(late.pk)
        assert late.payment_status == Order.PaymentStatus.PAID
        assert late.needs_attention and late.status == S.CANCELLED
        assert stock(variant) == (0, 0)  # never negative
        assert confirm_payment(late.pk).needs_attention  # idempotent


class TestStatus:
    def test_happy_path_logged(self, en, owner):
        order = confirm_payment(order_for(piece()).pk)
        for to in (S.PROCESSING, S.SHIPPED, S.DELIVERED):
            order = change_status(order, to, by=owner)
        assert list(order.history.values_list("to_status", flat=True)) == [
            S.AWAITING_PAYMENT,
            S.NEW,
            S.PROCESSING,
            S.SHIPPED,
            S.DELIVERED,
        ]
        assert order.history.last().changed_by == owner

    @pytest.mark.parametrize(
        "path",
        [(S.SHIPPED,), (S.DELIVERED,), (S.PROCESSING, S.NEW), (S.CANCELLED, S.NEW)],
    )
    def test_forbidden(self, en, path):
        order = confirm_payment(order_for(piece()).pk)
        *ok, bad = path
        for to in ok:
            order = change_status(order, to)
        with pytest.raises(InvalidTransition):
            change_status(order, bad)

    def test_customer_note_on_shipping(self, en):
        order = confirm_payment(order_for(piece()).pk)
        order = change_status(order, S.PROCESSING)
        order = change_status(order, S.SHIPPED, customer_note="  Tomorrow 12–15  ")
        assert order.customer_note == "Tomorrow 12–15"

    def test_cancel_paid_returns_pieces_to_the_shop(self, en):
        variant = piece()
        order = confirm_payment(order_for(variant).pk)
        change_status(order, S.CANCELLED)
        assert stock(variant) == (1, 0)
        product = Product.objects.get(pk=variant.product_id)
        assert product.status == Product.Status.ACTIVE and product.sold_at is None

    def test_cancel_paid_keeping_pieces_out(self, en):
        variant = piece()
        order = confirm_payment(order_for(variant).pk)
        change_status(order, S.CANCELLED, return_to_shop=False)
        assert stock(variant) == (0, 0)

    def test_cancel_unpaid_releases_hold(self, en):
        variant = piece()
        order = change_status(order_for(variant), S.CANCELLED)
        assert stock(variant) == (1, 0) and order.payment_status == Order.PaymentStatus.FAILED

    def test_refund_only_for_paid_cancelled(self, en):
        order = confirm_payment(order_for(piece()).pk)
        with pytest.raises(InvalidTransition):
            mark_refunded(order)
        order = change_status(order, S.CANCELLED)
        order = mark_refunded(order, note="Refunded in the BOG portal")
        assert order.payment_status == Order.PaymentStatus.REFUNDED
        assert order.history.last().note == "Refunded in the BOG portal"

    def test_resolve_attention(self, en):
        order = order_for(piece())
        Order.objects.filter(pk=order.pk).update(needs_attention=True)
        order = resolve_attention(order, note="Refunded")
        assert not order.needs_attention
        assert OrderStatusHistory.objects.filter(order=order, note="Refunded").exists()


def test_fake_session_is_isolated():
    assert FakeSession() == {}
