import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.checks import run_checks
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.providers import get_provider
from apps.payments.services import expire_overdue, start_payment, sync_status
from apps.payments.tasks import expire_reservations
from tests.orders.helpers import order_for, piece

pytestmark = pytest.mark.django_db
HTMX = {"HTTP_HX_REQUEST": "true"}


def started(variant=None, **kwargs):
    order = order_for(variant or piece(), **kwargs)
    url = start_payment(order, RequestFactory().get("/"))
    payment = order.payments.get()
    return order, payment, url


def callback(client, body):
    return client.post("/payments/callback/fake/", body, content_type="application/json")


def refreshed(obj):
    obj.refresh_from_db()
    return obj


class TestStart:
    def test_payment_created_and_redirect_to_hosted_page(self, en):
        order, payment, url = started()
        assert payment.provider == "fake" and payment.amount == order.total
        assert payment.provider_order_id.startswith("fake-")
        assert url == f"/en/payments/fake/{payment.provider_order_id}/"
        assert payment.raw_request["return_url"].endswith(order.get_absolute_url())
        assert payment.raw_request["callback_url"].endswith("/payments/callback/fake/")


class TestCallback:
    def test_signed_paid_callback_confirms(self, client, en):
        order, payment, _ = started()
        body = get_provider("fake").callback_body(payment.provider_order_id, "paid")
        assert callback(client, body).status_code == 200
        order = refreshed(order)
        assert (order.status, order.payment_status) == ("new", "paid")
        assert refreshed(payment).status == "paid"
        assert len(refreshed(payment).raw_callbacks) == 1

    def test_repeated_callbacks_are_harmless(self, client, en):
        variant = piece(unique=False, stock=3)
        order, payment, _ = started(variant)
        body = get_provider("fake").callback_body(payment.provider_order_id, "paid")
        for _ in range(3):
            assert callback(client, body).status_code == 200
        variant.refresh_from_db()
        assert (variant.stock, variant.reserved) == (2, 0)
        assert refreshed(order).history.count() == 2
        assert len(refreshed(payment).raw_callbacks) == 3  # every payload kept

    def test_failure_after_success_is_ignored(self, client, en):
        order, payment, _ = started()
        provider = get_provider("fake")
        callback(client, provider.callback_body(payment.provider_order_id, "paid"))
        callback(client, provider.callback_body(payment.provider_order_id, "failed"))
        assert refreshed(order).status == "new" and refreshed(payment).status == "paid"

    def test_success_after_failure_is_accepted_while_free(self, client, en):
        order, payment, _ = started()
        provider = get_provider("fake")
        callback(client, provider.callback_body(payment.provider_order_id, "failed"))
        assert refreshed(order).status == "cancelled"
        callback(client, provider.callback_body(payment.provider_order_id, "paid"))
        assert refreshed(order).status == "new"

    def test_bad_signature_is_rejected(self, client, en):
        order, payment, _ = started()
        forged = json.dumps(
            {"reference": payment.provider_order_id, "status": "paid", "signature": "0" * 64}
        )
        assert callback(client, forged).status_code == 400
        assert callback(client, "not json").status_code == 400
        assert refreshed(order).status == "awaiting_payment"

    def test_unknown_reference_and_provider(self, client):
        body = get_provider("fake").callback_body("fake-nope", "paid")
        assert callback(client, body).status_code == 404
        assert (
            client.post(
                "/payments/callback/nope/", "{}", content_type="application/json"
            ).status_code
            == 404
        )

    def test_callback_needs_no_csrf_but_only_post(self, en):
        from django.test import Client

        order, payment, _ = started()
        strict = Client(enforce_csrf_checks=True)
        body = get_provider("fake").callback_body(payment.provider_order_id, "paid")
        assert (
            strict.post(
                "/payments/callback/fake/", body, content_type="application/json"
            ).status_code
            == 200
        )
        assert strict.get("/payments/callback/fake/").status_code == 405


class TestFakeBank:
    def test_pay(self, client, en):
        order, payment, url = started()
        page = client.get(url).content.decode()
        assert "Test payment" in page and order.number in page
        response = client.post(url, {"decision": "paid"})
        assert response["Location"] == order.get_absolute_url()
        assert refreshed(order).status == "new"

    def test_decline(self, client, en):
        order, _, url = started()
        client.post(url, {"decision": "failed"})
        order = refreshed(order)
        assert (order.status, order.cancel_reason) == ("cancelled", "payment_failed")

    def test_delay_is_found_by_polling(self, client, en, monkeypatch):
        order, payment, url = started()
        client.post(url, {"decision": "delay"})
        assert sync_status(refreshed(order)).status == "awaiting_payment"
        later = timezone.now() + timedelta(seconds=20)
        monkeypatch.setattr("apps.payments.providers.fake.timezone.now", lambda: later)
        assert sync_status(refreshed(order)).status == "new"

    def test_hidden_when_fake_is_off(self, client, en, settings):
        _, _, url = started()
        settings.PAYMENT_PROVIDERS = {"bog": "bog", "tbc": "tbc"}
        assert client.get(url).status_code == 404


class TestExpiry:
    def test_overdue_orders_are_released(self, en):
        variant = piece()
        order = order_for(variant)
        start_payment(order, RequestFactory().get("/"))
        Order.objects.filter(pk=order.pk).update(
            reservation_expires_at=timezone.now() - timedelta(minutes=1)
        )
        assert expire_overdue() == 1
        order = refreshed(order)
        assert (order.status, order.cancel_reason) == ("cancelled", "expired")
        variant.refresh_from_db()
        assert variant.reserved == 0

    def test_last_check_with_the_bank_before_expiring(self, en):
        order, payment, _ = started()
        get_provider("fake").decide(payment, "paid")  # paid, but the callback got lost
        Order.objects.filter(pk=order.pk).update(
            reservation_expires_at=timezone.now() - timedelta(minutes=1)
        )
        assert expire_overdue() == 0
        assert refreshed(order).status == "new"

    def test_not_yet_due_is_kept(self, en):
        started()
        assert expire_overdue() == 0

    def test_task_and_command(self, en):
        order = order_for(piece())
        Order.objects.filter(pk=order.pk).update(
            reservation_expires_at=timezone.now() - timedelta(minutes=1)
        )
        assert expire_reservations.call_local() == 1
        out = StringIO()
        call_command("expire_reservations", stdout=out)
        assert "0 order(s) expired." in out.getvalue()


class TestFakeProviderGuard:
    def test_error_outside_dev_and_tests(self, settings):
        settings.PAYMENTS_ALLOW_FAKE = False
        assert [e.id for e in run_checks(tags=["payments"])] == ["payments.E001"]

    def test_fine_in_tests(self):
        assert run_checks(tags=["payments"]) == []


class TestOrderPage:
    def test_waiting_page_polls(self, client, en):
        order, _, _ = started()
        page = client.get(order.get_absolute_url()).content.decode()
        assert "Waiting for the bank" in page
        assert 'hx-trigger="every 3s"' in page and "?poll=1" in page
        assert '<meta name="robots" content="noindex' in page

    def test_polling_stops_after_a_minute(self, client, en):
        order, _, _ = started()
        html = client.get(order.get_absolute_url() + "?poll=20", **HTMX).content.decode()
        assert "Still waiting for confirmation" in html and "hx-trigger" not in html

    def test_paid_page(self, client, en):
        order, payment, url = started()
        client.post(url, {"decision": "paid"})
        response = client.get(order.get_absolute_url())
        page = response.content.decode()
        assert "Thank you" in page and order.number in page and "hx-trigger" not in page
        assert response["Cache-Control"] == "private, no-store"
        assert response["Referrer-Policy"] == "no-referrer"

    def test_failed_and_expired_pages(self, client, en):
        order, _, url = started()
        client.post(url, {"decision": "failed"})
        assert "did not go through" in client.get(order.get_absolute_url()).content.decode()
        expired = order_for(piece())
        Order.objects.filter(pk=expired.pk).update(
            reservation_expires_at=timezone.now() - timedelta(minutes=1)
        )
        page = client.get(expired.get_absolute_url()).content.decode()  # expires on view
        assert "The time to pay ran out" in page

    def test_headline_follows_the_status(self, client, en):
        from apps.orders.services import change_status, confirm_payment

        order = confirm_payment(order_for(piece()).pk)
        for to in ("processing", "shipped"):
            order = change_status(order, to)
        page = client.get(order.get_absolute_url()).content.decode()
        assert "On its way" in page and "confirmation is on its way" not in page

    def test_unknown_token_404(self, client, en):
        assert client.get("/en/order/00000000-0000-0000-0000-000000000000/").status_code == 404

    def test_payment_without_provider_reference_is_not_queried(self, en):
        order = order_for(piece())
        Payment.objects.create(order=order, provider="fake", amount=order.total)
        assert sync_status(order).status == "awaiting_payment"
