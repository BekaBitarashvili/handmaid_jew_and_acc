"""Which provider handles which payment method (settings.PAYMENT_PROVIDERS).

Phase 1d routes both BOG and TBC to the fake provider; 1e adds the real ones.
"""

from django.conf import settings

from .base import CallbackData, CreatedPayment, InvalidCallback, PaymentProvider, PaymentState
from .fake import FakeProvider

PROVIDERS: dict[str, type] = {"fake": FakeProvider}


def provider_for_method(method: str) -> PaymentProvider:
    return get_provider(settings.PAYMENT_PROVIDERS[method])


def get_provider(code: str) -> PaymentProvider:
    try:
        return PROVIDERS[code]()
    except KeyError as error:
        raise LookupError(f"unknown payment provider {code!r}") from error


def fake_enabled() -> bool:
    return "fake" in settings.PAYMENT_PROVIDERS.values()


__all__ = [
    "CallbackData",
    "CreatedPayment",
    "InvalidCallback",
    "PaymentProvider",
    "PaymentState",
    "fake_enabled",
    "get_provider",
    "provider_for_method",
]
