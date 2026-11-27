"""Fake provider for development and tests (SPEC §8): a local "bank" page where the tester
chooses success, failure or a delayed success. It follows the same contract as BOG / TBC:
a hosted page, a signed server-to-server callback and a status query.

Never enabled in production (system check `payments.E001`).
"""

import hashlib
import hmac
import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .base import CallbackData, CreatedPayment, InvalidCallback, PaymentState

DELAY_SECONDS = 15


def _signature(body: bytes) -> str:
    key = f"{settings.SECRET_KEY}:fake-payments".encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


class FakeProvider:
    code = "fake"

    def create_payment(self, payment, return_url: str, callback_url: str) -> CreatedPayment:
        reference = f"fake-{uuid.uuid4().hex[:20]}"
        return CreatedPayment(
            redirect_url=reverse("payments:fake_bank", kwargs={"reference": reference}),
            provider_order_id=reference,
            raw={
                "amount": payment.amount,
                "return_url": return_url,
                "callback_url": callback_url,
                "fake": {"decision": None, "paid_after": None},
            },
        )

    # --- the "bank" side -------------------------------------------------------------

    def decide(self, payment, decision: str) -> bytes | None:
        """The tester's choice on the fake bank page. Returns the signed callback body the
        bank would POST (None for the delayed case: that one is found by polling)."""
        state = payment.raw_request.setdefault("fake", {})
        state["decision"] = decision
        if decision == "delay":
            state["paid_after"] = (timezone.now() + timedelta(seconds=DELAY_SECONDS)).isoformat()
        payment.save(update_fields=["raw_request", "updated_at"])
        if decision == "delay":
            return None
        return self.callback_body(payment.provider_order_id, decision)

    def callback_body(self, reference: str, status: str) -> bytes:
        payload = {"reference": reference, "status": status}
        body = json.dumps(payload, sort_keys=True).encode()
        return json.dumps({**payload, "signature": _signature(body)}).encode()

    # --- the shop side -----------------------------------------------------------------

    def verify_callback(self, request) -> CallbackData:
        return self.verify_body(request.body)

    def verify_body(self, body: bytes) -> CallbackData:
        try:
            data = json.loads(body)
            payload = {"reference": data["reference"], "status": data["status"]}
            signature = data["signature"]
        except (ValueError, KeyError, TypeError) as error:
            raise InvalidCallback("malformed") from error
        expected = _signature(json.dumps(payload, sort_keys=True).encode())
        if not hmac.compare_digest(expected, str(signature)):
            raise InvalidCallback("bad signature")
        states = {"paid": PaymentState.PAID, "failed": PaymentState.FAILED}
        if payload["status"] not in states:
            raise InvalidCallback("unknown status")
        return CallbackData(
            provider_order_id=payload["reference"], state=states[payload["status"]], raw=payload
        )

    def fetch_status(self, provider_order_id: str) -> PaymentState:
        from ..models import Payment

        payment = Payment.objects.filter(provider=self.code, provider_order_id=provider_order_id)
        payment = payment.first()
        if payment is None:
            return PaymentState.PENDING
        state = payment.raw_request.get("fake", {})
        decision = state.get("decision")
        if decision == "paid":
            return PaymentState.PAID
        if decision == "failed":
            return PaymentState.FAILED
        if decision == "delay" and state.get("paid_after"):
            ready = timezone.now().isoformat() >= state["paid_after"]
            return PaymentState.PAID if ready else PaymentState.PENDING
        return PaymentState.PENDING
