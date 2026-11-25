"""Sales (SPEC §5 promotions), pulled forward from Phase 3. Promo codes stay in Phase 3."""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Category, Product
from apps.core.fields import MoneyField


class SaleQuerySet(models.QuerySet):
    def running(self, now=None):
        """Switched on and inside their date window."""
        now = now or timezone.now()
        return self.filter(is_active=True, starts_at__lte=now).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now)
        )


class Sale(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", _("Percent off")
        FIXED = "fixed", _("Fixed amount off (₾)")

    name = models.CharField(
        _("internal name"), max_length=100, help_text=_('Only you see this, e.g. "Spring 2026".')
    )
    discount_type = models.CharField(
        _("discount type"),
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
    )
    percent = models.PositiveSmallIntegerField(
        _("percent off"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
    )
    amount = MoneyField(_("amount off (₾)"), null=True, blank=True)

    applies_to_all = models.BooleanField(_("the whole shop"), default=False)
    products = models.ManyToManyField(
        Product, verbose_name=_("products"), blank=True, related_name="sales"
    )
    categories = models.ManyToManyField(
        Category,
        verbose_name=_("categories"),
        blank=True,
        related_name="sales",
        help_text=_("Subcategories are included."),
    )

    starts_at = models.DateTimeField(_("starts"), default=timezone.now)
    ends_at = models.DateTimeField(
        _("ends"), null=True, blank=True, help_text=_("Empty = until you switch it off.")
    )
    is_active = models.BooleanField(_("switched on"), default=True)

    # "Special Offers" banner on the home page.
    show_on_home = models.BooleanField(
        _("show the banner on the home page"),
        default=False,
        help_text=_("Shown only while the sale is running."),
    )
    banner_title = models.CharField(_("banner title"), max_length=80, blank=True)
    banner_subtitle = models.CharField(_("banner subtitle"), max_length=160, blank=True)
    banner_image = models.ImageField(_("banner photo"), upload_to="banners/", blank=True)

    created_at = models.DateTimeField(_("created"), auto_now_add=True)

    objects = SaleQuerySet.as_manager()

    class Meta:
        verbose_name = _("sale")
        verbose_name_plural = _("sales")
        ordering = ("-starts_at", "-pk")

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        errors = {}
        if self.discount_type == self.DiscountType.PERCENT and not self.percent:
            errors["percent"] = _("Enter the percent off.")
        if self.discount_type == self.DiscountType.FIXED and not self.amount:
            errors["amount"] = _("Enter the amount off.")
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = _("The end must be after the start.")
        if errors:
            raise ValidationError(errors)

    @property
    def is_running(self) -> bool:
        now = timezone.now()
        return (
            self.is_active
            and self.starts_at <= now
            and (self.ends_at is None or self.ends_at > now)
        )
