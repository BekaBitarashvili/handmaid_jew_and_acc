import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
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

    @property
    def fixed_city(self) -> str:
        """Courier in Tbilisi delivers in Tbilisi only: no city field at checkout."""
        return str(_("Tbilisi")) if self.code == TBILISI_COURIER else ""


TBILISI_COURIER = "courier_tbilisi"


class Order(models.Model):
    """A guest order (SPEC §5). Money in tetri; names and prices are snapshots, so later
    catalog changes never rewrite what the customer bought."""

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", _("Awaiting payment")
        NEW = "new", _("New")
        PROCESSING = "processing", _("Being prepared")
        SHIPPED = "shipped", _("Shipped")
        DELIVERED = "delivered", _("Delivered")
        CANCELLED = "cancelled", _("Cancelled")

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")

    class PaymentMethod(models.TextChoices):
        BOG = "bog", _("Bank of Georgia")
        TBC = "tbc", _("TBC Bank")

    number = models.CharField(_("order number"), max_length=12, unique=True)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    language = models.CharField(_("language"), max_length=5, default="ka")
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT
    )
    payment_status = models.CharField(
        _("payment"), max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    payment_method = models.CharField(
        _("payment method"), max_length=10, choices=PaymentMethod.choices
    )

    # Customer (the buyer may live anywhere; phones are stored in E.164).
    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"))
    phone = models.CharField(_("phone"), max_length=20)

    # Delivery (Georgia only). The option fields are snapshots of the option chosen.
    delivery_option = models.ForeignKey(
        DeliveryOption,
        verbose_name=_("delivery"),
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
    )
    delivery_name = models.CharField(_("delivery"), max_length=100)
    delivery_code = models.CharField(max_length=30)
    requires_address = models.BooleanField(default=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    address_line = models.CharField(_("address"), max_length=255, blank=True)
    delivery_notes = models.TextField(_("delivery notes"), blank=True)
    recipient_name = models.CharField(_("recipient name"), max_length=150, blank=True)
    recipient_phone = models.CharField(_("recipient phone"), max_length=20, blank=True)

    # Gift.
    gift_wrap = models.BooleanField(_("gift wrap"), default=False)
    gift_note = models.TextField(_("gift note"), max_length=300, blank=True)
    hide_prices_on_slip = models.BooleanField(_("hide prices on the packing slip"), default=False)

    # Totals (tetri).
    subtotal = MoneyField(_("pieces"), default=0)
    savings = MoneyField(_("sale savings"), default=0)
    gift_wrap_price = MoneyField(_("gift wrap"), default=0)
    shipping_price = MoneyField(_("delivery"), default=0)
    total = MoneyField(_("total"), default=0)

    # Consents (SPEC §11): stored with the time they were given.
    consent_terms = models.BooleanField(_("accepted the terms"), default=False)
    consent_privacy = models.BooleanField(_("accepted the privacy policy"), default=False)
    consent_marketing = models.BooleanField(_("agreed to news by email"), default=False)
    consented_at = models.DateTimeField(_("consents given"), null=True, blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("browser"), max_length=300, blank=True)

    reservation_expires_at = models.DateTimeField(_("pieces held until"), null=True, blank=True)
    paid_at = models.DateTimeField(_("paid"), null=True, blank=True)
    customer_note = models.TextField(
        _("note for the customer"),
        blank=True,
        help_text=_("Shown on the order page and in the shipped email, e.g. a delivery time."),
    )
    internal_notes = models.TextField(
        _("internal notes"), blank=True, help_text=_("Only you see these.")
    )
    needs_attention = models.BooleanField(_("needs attention"), default=False)
    attention_reason = models.TextField(_("what needs attention"), blank=True)
    created_at = models.DateTimeField(_("placed"), auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "reservation_expires_at"]),
            models.Index(fields=["needs_attention"]),
        ]

    def __str__(self) -> str:
        return self.number

    def get_absolute_url(self) -> str:
        return reverse("orders:detail", kwargs={"token": self.public_token})

    @property
    def customer_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def has_recipient(self) -> bool:
        return bool(self.recipient_name or self.recipient_phone)

    @property
    def is_paid(self) -> bool:
        return self.payment_status in (self.PaymentStatus.PAID, self.PaymentStatus.REFUNDED)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        "catalog.ProductVariant", verbose_name=_("variant"), on_delete=models.PROTECT
    )
    product_name = models.CharField(_("product"), max_length=200)
    variant_name = models.CharField(_("variant"), max_length=100, blank=True)
    sku = models.CharField(_("code"), max_length=40)
    original_unit_price = MoneyField(_("price before sale"), default=0)
    unit_price = MoneyField(_("price"))
    qty = models.PositiveSmallIntegerField(_("quantity"))
    line_total = MoneyField(_("total"))
    image_url = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = _("item")
        verbose_name_plural = _("items")
        ordering = ("pk",)

    def __str__(self) -> str:
        return f"{self.product_name} × {self.qty}"

    @property
    def on_sale(self) -> bool:
        return self.unit_price < self.original_unit_price


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(_("from"), max_length=20, blank=True)
    to_status = models.CharField(_("to"), max_length=20)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    note = models.TextField(_("note"), blank=True)
    created_at = models.DateTimeField(_("when"), auto_now_add=True)

    class Meta:
        verbose_name = _("status change")
        verbose_name_plural = _("status history")
        ordering = ("created_at", "pk")

    def __str__(self) -> str:
        return f"{self.order}: {self.from_status or '—'} → {self.to_status}"

    @property
    def to_label(self) -> str:
        return Order.Status(self.to_status).label


class OrderNumberSequence(models.Model):
    """Per-year counter behind order numbers: 26-1001, 26-1002, … (restarts each year)."""

    FIRST_NUMBER = 1001

    year = models.PositiveSmallIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=FIRST_NUMBER - 1)

    def __str__(self) -> str:
        return f"{self.year}: {self.last_number}"
