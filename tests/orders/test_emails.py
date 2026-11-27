import pytest
from django.core import mail

from apps.core.models import SiteSettings
from apps.orders.models import Order
from apps.orders.services import change_status, confirm_payment, fail_payment
from apps.orders.services.checkout import place_order

from .helpers import cart_with, data, order_for, piece

pytestmark = pytest.mark.django_db
S = Order.Status


@pytest.fixture(autouse=True)
def owner_email():
    site = SiteSettings.load()
    site.owner_notification_email = "owner@example.com"
    site.contact_email = "hello@example.com"
    site.save()


@pytest.fixture
def run(django_capture_on_commit_callbacks):
    """Run a service and the emails it schedules after commit."""

    def runner(func, *args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return func(*args, **kwargs)

    return runner


def html(message) -> str:
    return message.alternatives[0][0]


def paid_order(run, **kwargs):
    variant = piece(
        name_en="Amber necklace",
        name_ka="ქარვის ყელსაბამი",
        care_instructions_en="Keep it dry and away from perfume.",
    )
    order = order_for(variant, **kwargs)
    return run(confirm_payment, order.pk)


class TestPaid:
    def test_customer_and_owner(self, run, en):
        order = paid_order(run)
        customer, owner = mail.outbox
        assert customer.to == ["nino@example.com"] and owner.to == ["owner@example.com"]
        assert customer.subject == f"Thank you for your order {order.number}"
        assert customer.reply_to == ["hello@example.com"] and owner.reply_to == ["nino@example.com"]
        body = html(customer)
        assert (
            "Amber necklace" in body
            and f"http://127.0.0.1:8000/en/order/{order.public_token}/" in body
        )
        assert "font-style:italic" in body  # English heading
        assert "Amber necklace" in customer.body  # plain-text alternative
        assert "+995 555 12 34 56" in html(owner)  # admin link: tests/orders/test_admin.py

    def test_customer_email_in_the_order_language(self, run):
        cart = cart_with(piece(name_en="Amber necklace", name_ka="ქარვის ყელსაბამი"))
        order = place_order(cart, data(), language="ka")
        run(confirm_payment, order.pk)
        customer = mail.outbox[0]
        assert "ქარვის ყელსაბამი" in html(customer) and "/ka/order/" in html(customer)
        assert "font-style:italic" not in html(customer).split("<h1", 1)[1].split(">", 1)[0]

    def test_sent_once(self, run, en):
        order = paid_order(run)
        run(confirm_payment, order.pk)
        assert len(mail.outbox) == 2

    def test_no_owner_address_only_customer(self, run, en):
        SiteSettings.objects.update(owner_notification_email="", contact_email="")
        paid_order(run)
        assert [m.to for m in mail.outbox] == [["nino@example.com"]]

    def test_gift_and_recipient_shown(self, run, en):
        paid_order(run, gift_wrap=True, gift_note="Happy birthday", recipient_name="Tamar")
        assert "Happy birthday" in html(mail.outbox[0]) and "Tamar" in html(mail.outbox[1])


class TestStatusEmails:
    def test_shipped_with_note(self, run, en):
        order = paid_order(run)
        mail.outbox.clear()
        order = run(change_status, order, S.PROCESSING)
        assert mail.outbox == []
        run(change_status, order, S.SHIPPED, customer_note="Tomorrow between 12 and 15")
        (shipped,) = mail.outbox
        assert "is on its way" in shipped.subject
        assert "Tomorrow between 12 and 15" in html(shipped) and "Tomorrow" in shipped.body

    def test_delivered_with_care_tips(self, run, en):
        order = paid_order(run)
        for to in (S.PROCESSING, S.SHIPPED):
            order = run(change_status, order, to)
        mail.outbox.clear()
        run(change_status, order, S.DELIVERED)
        (delivered,) = mail.outbox
        assert "has arrived" in delivered.subject
        assert "Caring for your pieces" in html(delivered)
        assert "Keep it dry and away from perfume." in html(delivered)

    def test_cancelled_paid_tells_both(self, run, en):
        order = paid_order(run)
        mail.outbox.clear()
        run(change_status, order, S.CANCELLED, customer_note="The clasp broke; refunded.")
        customer, owner = mail.outbox
        assert "was cancelled" in customer.subject and "The clasp broke" in html(customer)
        assert "მერჩანტ-პორტალში" in html(owner)  # owner emails are Georgian (refund reminder)

    def test_unpaid_cancellation_sends_nothing(self, run, en):
        run(fail_payment, order_for(piece()).pk)
        assert mail.outbox == []


def test_needs_attention_goes_to_the_owner_only(run, en):
    variant = piece()
    late = order_for(variant)
    run(fail_payment, late.pk, expired=True)
    run(confirm_payment, order_for(variant).pk)
    mail.outbox.clear()
    run(confirm_payment, late.pk)
    (alert,) = mail.outbox
    assert alert.to == ["owner@example.com"] and late.number in alert.subject
    assert html(alert).count("9e3b2e") == 1  # the reason, highlighted


@pytest.mark.parametrize("lang", ["ka", "en"])
def test_no_template_syntax_in_emails(run, lang):
    order = place_order(cart_with(piece()), data(gift_note="Hi"), language=lang)
    order = run(confirm_payment, order.pk)
    for to in (S.PROCESSING, S.SHIPPED, S.DELIVERED):
        order = run(change_status, order, to, customer_note="Note")
    for message in mail.outbox:
        for part in (message.body, html(message)):
            for token in ("{%", "%}", "{{", "}}", "{#", "#}"):
                assert token not in part.replace("{{BRAND}}", ""), (message.subject, token)
