from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField


class Payment(models.Model):
    """One payment attempt with a provider (SPEC §5 payments). Never holds card data; raw
    requests and callbacks are kept (without secrets) for auditing."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")

    order = models.ForeignKey(
        "orders.Order", verbose_name=_("order"), on_delete=models.CASCADE, related_name="payments"
    )
    provider = models.CharField(_("provider"), max_length=10)
    provider_order_id = models.CharField(_("provider reference"), max_length=100, blank=True)
    amount = MoneyField(_("amount"))
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    raw_request = models.JSONField(default=dict, blank=True)
    raw_callbacks = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_order_id"],
                condition=~Q(provider_order_id=""),
                name="payment_provider_reference_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.provider_order_id or self.pk}"
