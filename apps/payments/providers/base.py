"""The contract every payment provider implements (SPEC §8). Providers never see or store
card data: the customer pays on the bank's hosted page."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from django.http import HttpRequest


class PaymentState(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


@dataclass
class CreatedPayment:
    redirect_url: str  # the bank's hosted payment page
    provider_order_id: str
    raw: dict = field(default_factory=dict)  # request/response for auditing, no secrets


@dataclass
class CallbackData:
    provider_order_id: str
    state: PaymentState
    raw: dict = field(default_factory=dict)


class InvalidCallback(Exception):
    """Signature or payload didn't check out; nothing may change."""


class PaymentProvider(Protocol):
    code: str

    def create_payment(self, payment, return_url: str, callback_url: str) -> CreatedPayment: ...

    def fetch_status(self, provider_order_id: str) -> PaymentState: ...

    def verify_callback(self, request: HttpRequest) -> CallbackData: ...
