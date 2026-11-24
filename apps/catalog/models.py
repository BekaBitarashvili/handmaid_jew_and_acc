"""Catalog data model (SPEC §5). Business rules live in apps/catalog/services/."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField, RichTextField

NEW_PRODUCT_DAYS = 30

code_validator = RegexValidator(r"^[A-Z]{3}$", _("Exactly 3 capital Latin letters, e.g. NEC."))
color_validator = RegexValidator(r"^#[0-9A-Fa-f]{6}$", _("A hex color like #C8862A."))


class Category(models.Model):
    name = models.CharField(_("name"), max_length=100)
    slug = models.SlugField(
        _("URL slug"),
        max_length=120,
        blank=True,
        help_text=_("Filled in automatically from the name when left empty."),
    )
    description = models.TextField(_("description"), blank=True)
    code = models.CharField(
        _("SKU code"),
        max_length=3,
        unique=True,
        validators=[code_validator],
        help_text=_("3 letters that start every product code in this category, e.g. NEC."),
    )
    image = models.ImageField(_("image"), upload_to="categories/", blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("parent category"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        help_text=_("Only top-level categories can be parents (two levels at most)."),
    )
    sort_order = models.PositiveIntegerField(_("order"), default=0, db_index=True)
    is_active = models.BooleanField(_("visible in the shop"), default=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ("sort_order", "pk")
        # Unique per language. The untranslated `slug` column follows whichever
        # language was active when saving, so it cannot carry a unique index.
        constraints = [
            models.UniqueConstraint(fields=["slug_ka"], name="category_unique_slug_ka"),
            models.UniqueConstraint(fields=["slug_en"], name="category_unique_slug_en"),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.parent_id is None:
            return
        if self.parent_id == self.pk:
            raise ValidationError({"parent": _("A category cannot be its own parent.")})
        if self.parent.parent_id is not None:
            raise ValidationError({"parent": _("Categories can be at most two levels deep.")})
        if self.pk and self.children.exists():
            raise ValidationError(
                {"parent": _("This category has subcategories, so it must stay top-level.")}
            )


class Stone(models.Model):
    name = models.CharField(_("name"), max_length=100)
    slug = models.SlugField(_("URL slug"), max_length=120, blank=True)
    short_description = models.CharField(_("short description"), max_length=255, blank=True)
    story = RichTextField(
        _("story"), blank=True, help_text=_("Origin, history and character of the stone.")
    )
    image = models.ImageField(_("image"), upload_to="stones/", blank=True)
    color_hex = models.CharField(
        _("color"),
        max_length=7,
        blank=True,
        validators=[color_validator],
        help_text=_("Used for small color swatches, e.g. #C8862A."),
    )
    sort_order = models.PositiveIntegerField(_("order"), default=0, db_index=True)

    class Meta:
        verbose_name = _("stone")
        verbose_name_plural = _("stones")
        ordering = ("sort_order", "pk")
        # Unique per language. The untranslated `slug` column follows whichever
        # language was active when saving, so it cannot carry a unique index.
        constraints = [
            models.UniqueConstraint(fields=["slug_ka"], name="stone_unique_slug_ka"),
            models.UniqueConstraint(fields=["slug_en"], name="stone_unique_slug_en"),
        ]

    def __str__(self) -> str:
        return self.name


class Material(models.Model):
    name = models.CharField(_("name"), max_length=100)
    sort_order = models.PositiveIntegerField(_("order"), default=0, db_index=True)

    class Meta:
        verbose_name = _("material")
        verbose_name_plural = _("materials")
        ordering = ("sort_order", "pk")

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        HIDDEN = "hidden", _("Hidden")
        SOLD = "sold", _("Sold (archive)")

    class NewBadge(models.TextChoices):
        AUTO = "auto", _("Automatic (first 30 days after publishing)")
        YES = "yes", _("Always show")
        NO = "no", _("Never show")

    sku = models.CharField(
        _("product code (SKU)"),
        max_length=20,
        unique=True,
        blank=True,
        help_text=_(
            "Created automatically, e.g. NEC-2026-0001. Cannot be changed after the product is "
            "created."
        ),
    )
    name = models.CharField(_("name"), max_length=150)
    slug = models.SlugField(
        _("URL slug"),
        max_length=170,
        blank=True,
        help_text=_("Filled in automatically from the name when left empty."),
    )
    category = models.ForeignKey(
        Category, verbose_name=_("category"), on_delete=models.PROTECT, related_name="products"
    )
    stones = models.ManyToManyField(
        Stone, verbose_name=_("stones"), blank=True, related_name="products"
    )
    materials = models.ManyToManyField(
        Material, verbose_name=_("materials"), blank=True, related_name="products"
    )

    short_description = models.CharField(
        _("short description"),
        max_length=255,
        blank=True,
        help_text=_("One sentence shown under the name."),
    )
    description = RichTextField(_("description"), blank=True)
    story = RichTextField(_("story"), blank=True, help_text=_("How this piece was made."))
    care_instructions = models.TextField(_("care instructions"), blank=True)
    dimensions = models.CharField(
        _("dimensions"),
        max_length=200,
        blank=True,
        help_text=_('Free text, e.g. "Length 45 cm + 5 cm extender".'),
    )
    weight_g = models.PositiveIntegerField(_("weight (g)"), null=True, blank=True)
    hours_to_make = models.PositiveIntegerField(_("hours to make"), null=True, blank=True)

    price = MoneyField(_("price (₾)"), help_text=_("In lari, e.g. 145 or 145.50."))
    # compare_at_price is not stored: Phase 3 computes it from active sales (SPEC §5).

    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    is_unique = models.BooleanField(
        _("one of a kind"),
        default=True,
        help_text=_(
            "Checked: a single, unrepeatable piece — stock is always 1 and it moves to the "
            "archive once sold. Unchecked: you can make several identical pieces, so stock "
            "can be more than 1."
        ),
    )
    is_featured = models.BooleanField(_("featured"), default=False)
    new_badge = models.CharField(
        _('"New" label'), max_length=4, choices=NewBadge.choices, default=NewBadge.AUTO
    )
    allow_commission_request = models.BooleanField(
        _("allow 'commission a similar piece'"), default=True
    )

    seo_title = models.CharField(_("SEO title"), max_length=70, blank=True)
    seo_description = models.CharField(_("SEO description"), max_length=160, blank=True)

    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)
    published_at = models.DateTimeField(_("first published"), null=True, blank=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ("-created_at",)
        # Unique per language. The untranslated `slug` column follows whichever
        # language was active when saving, so it cannot carry a unique index.
        constraints = [
            models.UniqueConstraint(fields=["slug_ka"], name="product_unique_slug_ka"),
            models.UniqueConstraint(fields=["slug_en"], name="product_unique_slug_en"),
        ]
        indexes = [models.Index(fields=["status", "-published_at"])]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        # Remember the stored SKU so the immutability guard needs no extra query.
        instance._loaded_sku = instance.__dict__.get("sku")
        return instance

    @property
    def is_new(self) -> bool:
        if self.new_badge == self.NewBadge.YES:
            return True
        if self.new_badge == self.NewBadge.NO or self.published_at is None:
            return False
        return timezone.now() - self.published_at < timedelta(days=NEW_PRODUCT_DAYS)

    @property
    def primary_image(self) -> "ProductImage | None":
        """The first image by sort order (prefetch `images` to avoid a query)."""
        images = list(self.images.all())
        return images[0] if images else None

    @property
    def total_stock(self) -> int:
        return sum(v.stock for v in self.variants.all())

    @property
    def total_available(self) -> int:
        return sum(v.available for v in self.variants.all())


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product, verbose_name=_("product"), on_delete=models.CASCADE, related_name="variants"
    )
    name = models.CharField(
        _("variant name"),
        max_length=100,
        blank=True,
        help_text=_('e.g. "Beige / M". Leave empty when the product has no variants.'),
    )
    sku_suffix = models.CharField(
        _("code suffix"), max_length=10, blank=True, help_text=_("Added to the product code.")
    )
    price_override = MoneyField(
        _("own price (₾)"),
        null=True,
        blank=True,
        help_text=_("Only if this variant costs differently from the product."),
    )
    stock = models.PositiveIntegerField(_("in stock"), default=1)
    reserved = models.PositiveIntegerField(
        _("reserved"), default=0, help_text=_("Held by unpaid orders; changes automatically.")
    )
    sort_order = models.PositiveIntegerField(_("order"), default=0, db_index=True)
    is_default = models.BooleanField(_("default"), default=False)

    class Meta:
        verbose_name = _("variant")
        verbose_name_plural = _("variants")
        ordering = ("sort_order", "pk")
        constraints = [
            models.CheckConstraint(
                condition=Q(reserved__lte=F("stock")), name="variant_reserved_lte_stock"
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_default=True),
                name="variant_one_default_per_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} — {self.name}" if self.name else str(self.product)

    @property
    def available(self) -> int:
        return self.stock - self.reserved

    @property
    def price(self) -> int:
        return self.price_override if self.price_override is not None else self.product.price

    @property
    def sku(self) -> str:
        return f"{self.product.sku}-{self.sku_suffix}" if self.sku_suffix else self.product.sku


def product_image_path(instance: "ProductImage", filename: str) -> str:
    now = timezone.now()
    return f"products/{now:%Y/%m}/{filename}"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, verbose_name=_("product"), on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(_("photo"), upload_to=product_image_path)
    alt = models.CharField(
        _("description for screen readers"),
        max_length=200,
        help_text=_('What the photo shows, e.g. "Amber necklace on linen, close-up".'),
    )
    sort_order = models.PositiveIntegerField(
        _("order"), default=0, db_index=True, help_text=_("The first photo is the main one.")
    )
    variant = models.ForeignKey(
        ProductVariant,
        verbose_name=_("variant"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="images",
        help_text=_("Show this photo when the variant is selected."),
    )

    class Meta:
        verbose_name = _("photo")
        verbose_name_plural = _("photos")
        ordering = ("sort_order", "pk")

    def __str__(self) -> str:
        return self.alt or self.image.name

    def clean(self) -> None:
        if self.variant_id and self.product_id and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": _("This variant belongs to another product.")})


class SkuSequence(models.Model):
    """Per-category, per-year counter behind product codes (NEC-2026-0001)."""

    prefix = models.CharField(max_length=3)
    year = models.PositiveSmallIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["prefix", "year"], name="sku_sequence_prefix_year")
        ]

    def __str__(self) -> str:
        return f"{self.prefix}-{self.year}: {self.last_number}"
