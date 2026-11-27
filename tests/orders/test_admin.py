import pytest
from django.core import mail
from django.urls import reverse

from apps.catalog.models import Product
from apps.core.models import SiteSettings
from apps.orders.models import Order
from apps.orders.services import confirm_payment, fail_payment

from .helpers import order_for, piece

pytestmark = pytest.mark.django_db
S = Order.Status


def url(name, *args):
    return reverse(f"admin:orders_order_{name}", args=args)


def text(response) -> str:
    assert response.status_code == 200, response.status_code
    return response.content.decode()


@pytest.fixture
def paid(django_capture_on_commit_callbacks):
    variant = piece(name_en="Amber necklace")
    with django_capture_on_commit_callbacks(execute=True):
        order = confirm_payment(order_for(variant, recipient_name="Tamar").pk)
    order.variant = variant
    return order


class TestList:
    def test_opens_on_needs_action(self, admin_client, paid):
        waiting = order_for(piece())
        page = text(admin_client.get(url("changelist")))
        assert paid.number in page and waiting.number not in page
        page = text(admin_client.get(url("changelist"), {"view": "all"}))
        assert waiting.number in page

    def test_flagged_orders_show_with_a_mark(self, admin_client):
        cancelled = fail_payment(order_for(piece()).pk)
        Order.objects.filter(pk=cancelled.pk).update(needs_attention=True)
        page = text(admin_client.get(url("changelist")))
        assert cancelled.number in page and "⚠" in page

    def test_search_by_phone_and_number(self, admin_client, paid):
        assert paid.number in text(
            admin_client.get(url("changelist"), {"q": "555123456", "view": "all"})
        )

    def test_staff_only_and_no_add_or_delete(self, client, admin_client, paid):
        assert client.get(url("changelist")).status_code == 302
        assert admin_client.get(url("add")).status_code == 403
        assert admin_client.get(url("delete", paid.pk)).status_code == 403


class TestDetail:
    def test_panel_with_actions_contacts_and_recipient(self, admin_client, paid):
        page = text(admin_client.get(url("change", paid.pk)))
        assert url("status", paid.pk, "processing") in page
        assert url("status", paid.pk, "cancelled") in page
        assert url("status", paid.pk, "shipped") not in page  # not the next step yet
        assert 'href="tel:+995555123456"' in page and 'href="mailto:nino@example.com' in page
        assert "order-contact--recipient" in page and "Tamar" in page
        assert url("slip", paid.pk) in page

    def test_georgian_by_default(self, admin_client, paid):
        admin_client.cookies.pop("django_language", None)
        page = text(admin_client.get(url("change", paid.pk)))
        assert '<html lang="ka"' in page

    def test_ship_with_a_note_for_the_customer(
        self, admin_client, paid, django_capture_on_commit_callbacks, admin_user
    ):
        admin_client.post(url("status", paid.pk, "processing"), {})
        form = text(admin_client.get(url("status", paid.pk, "shipped")))
        assert 'name="customer_note"' in form and 'name="return_to_shop"' not in form
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(
                url("status", paid.pk, "shipped"),
                {"customer_note": "Tomorrow 12–15", "note": "Courier Gio"},
            )
        assert response["Location"] == url("change", paid.pk)
        paid.refresh_from_db()
        assert (paid.status, paid.customer_note) == (S.SHIPPED, "Tomorrow 12–15")
        last = paid.history.last()
        assert (last.note, last.changed_by) == ("Courier Gio", admin_user)
        assert [m.to for m in mail.outbox] == [["nino@example.com"]]

    def test_cancel_returns_pieces_when_ticked(self, admin_client, paid):
        form = text(admin_client.get(url("status", paid.pk, "cancelled")))
        assert 'name="return_to_shop"' in form and "checked" in form  # ticked by default
        admin_client.post(url("status", paid.pk, "cancelled"), {"return_to_shop": "on"})
        paid.variant.refresh_from_db()
        assert paid.variant.stock == 1
        assert Product.objects.get(pk=paid.variant.product_id).status == Product.Status.ACTIVE

    def test_cancel_with_the_box_unticked_keeps_pieces_out(self, admin_client, paid):
        admin_client.post(url("status", paid.pk, "cancelled"), {"note": "Sold in person"})
        paid.variant.refresh_from_db()
        assert paid.variant.stock == 0
        assert Product.objects.get(pk=paid.variant.product_id).status == Product.Status.SOLD

    def test_forbidden_step_is_refused(self, admin_client, paid):
        response = admin_client.post(url("status", paid.pk, "delivered"), {}, follow=True)
        assert "This status change is not possible." in text(response)
        paid.refresh_from_db()
        assert paid.status == S.NEW

    def test_refund_and_resolve(self, admin_client, paid):
        admin_client.post(url("status", paid.pk, "cancelled"), {"return_to_shop": "on"})
        admin_client.post(url("refund", paid.pk), {"note": "BOG portal"})
        paid.refresh_from_db()
        assert paid.payment_status == "refunded"
        Order.objects.filter(pk=paid.pk).update(needs_attention=True, attention_reason="Late")
        page = text(admin_client.get(url("change", paid.pk)))
        assert "Late" in page and url("resolve", paid.pk) in page
        admin_client.post(url("resolve", paid.pk), {"note": "Called her"})
        paid.refresh_from_db()
        assert not paid.needs_attention


class TestSlip:
    def test_prices_shown_by_default(self, admin_client, paid):
        page = text(admin_client.get(url("slip", paid.pk)))
        assert "Amber necklace" in page and 'class="price"' in page and "₾" in page
        assert "Tamar" in page  # the recipient first

    def test_prices_hidden_and_gift_note(self, admin_client, django_capture_on_commit_callbacks):
        order = order_for(piece(name_en="Ring"), hide_prices_on_slip=True, gift_note="For you")
        order = confirm_payment(order.pk)
        page = text(admin_client.get(url("slip", order.pk)))
        assert "Ring" in page and "₾" not in page
        assert '<div class="note">For you</div>' in page


def test_owner_email_links_to_the_admin(django_capture_on_commit_callbacks):
    site = SiteSettings.load()
    site.owner_notification_email = "owner@example.com"
    site.save()
    with django_capture_on_commit_callbacks(execute=True):
        order = confirm_payment(order_for(piece()).pk)
    owner = mail.outbox[-1]
    assert f"http://127.0.0.1:8000{url('change', order.pk)}" in owner.alternatives[0][0]
