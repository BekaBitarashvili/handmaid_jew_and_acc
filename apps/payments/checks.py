from django.conf import settings
from django.core.checks import Error, register

from .providers import fake_enabled


@register("payments")
def fake_provider_not_in_production(app_configs, **kwargs):
    """The fake provider accepts any "payment": it must never run outside dev and tests."""
    if fake_enabled() and not getattr(settings, "PAYMENTS_ALLOW_FAKE", False):
        return [
            Error(
                "The fake payment provider is enabled outside development and tests.",
                hint="Route PAYMENT_PROVIDERS to real providers, or set PAYMENTS_ALLOW_FAKE "
                "only in dev/test settings.",
                id="payments.E001",
            )
        ]
    return []
