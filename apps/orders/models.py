from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField


class DeliveryOption(models.Model):
    """Configurable delivery methods with prices (SPEC §5 orders)."""

    name = models.CharField(_("name"), max_length=100)
    code = models.SlugField(
        _("code"),
        max_length=30,
        unique=True,
        help_text=_("Internal identifier, e.g. courier_tbilisi. Do not change once used."),
    )
    price = MoneyField(_("price (₾)"), default=0)
    free_over_threshold = models.BooleanField(
        _("free above the free-shipping threshold"),
        default=True,
        help_text=_("The threshold is set in Site settings."),
    )
    estimated_days = models.CharField(
        _("delivery time"), max_length=60, blank=True, help_text=_('e.g. "1–2 business days".')
    )
    requires_address = models.BooleanField(
        _("needs a delivery address"), default=True, help_text=_("Off for pickup.")
    )
    is_active = models.BooleanField(_("available at checkout"), default=True)
    sort_order = models.PositiveIntegerField(_("order"), default=0, db_index=True)

    class Meta:
        verbose_name = _("delivery option")
        verbose_name_plural = _("delivery options")
        ordering = ("sort_order", "pk")

    def __str__(self) -> str:
        return self.name
