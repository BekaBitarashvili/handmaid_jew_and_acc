"""Catalog admin (SPEC §10): phone-first product editing with ka/en tabs."""

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count, Max
from django.forms.models import BaseInlineFormSet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext, ngettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import (
    TabbedTranslationAdmin,
    TranslationStackedInline,
)
from unfold.admin import StackedInline
from unfold.decorators import display

from apps.core.admin_base import BaseModelAdmin, FormfieldDefaultsMixin
from apps.core.money import format_gel

from .images import admin_thumb
from .models import Category, Material, Product, ProductImage, ProductVariant, Stone
from .services import inventory
from .services.images import InvalidImageError, process_upload
from .services.products import (
    PublishCheck,
    duplicate_product,
    ensure_default_variant,
    prepare_product_for_save,
    publish_blockers,
    set_visibility,
)
from .services.slugs import fill_translated_slugs
from .tasks import generate_product_image_renditions

PHOTO_GUIDELINES = _(
    "Photo tips: square photos with the piece in the centre, the same calm backdrop (linen, "
    "paper, old wood or stone), daylight, at least 3 shots per piece — detail, full piece, "
    "worn. At least 2000px on each side."
)


def _thumb_html(image_field, size: int = 48):
    thumb = admin_thumb(image_field) if image_field else None
    if not thumb:
        return format_html(
            '<span class="block bg-base-100" style="width:{}px;height:{}px"></span>',
            size,
            size * 5 // 4,
        )
    return format_html(
        '<img src="{}" alt="" width="{}" height="{}" style="object-fit:cover">',
        thumb.url,
        size,
        size * 5 // 4,
    )


# --- Multi-photo upload -----------------------------------------------------


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True
    template_name = "catalog/widgets/multiple_photos.html"


class MultipleImageField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, list | tuple):
            return [single(item, initial) for item in data if item]
        return [single(data, initial)] if data else []


class ProductAdminForm(forms.ModelForm):
    new_photos = MultipleImageField(
        label=_("Add photos"),
        required=False,
        widget=MultipleFileInput(attrs={"accept": "image/*", "multiple": True}),
        help_text=PHOTO_GUIDELINES,
    )

    class Meta:
        model = Product
        # ModelAdmin narrows this to the fields in `fieldsets`.
        fields = "__all__"  # noqa: DJ007


# --- Inlines ----------------------------------------------------------------


class ProductImageFormSet(BaseInlineFormSet):
    """Runs the publish check: an Active product needs photos with Georgian alt text."""

    def clean(self):
        super().clean()
        product = self.instance
        if product.status != Product.Status.ACTIVE:
            return
        kept = [
            form
            for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get("DELETE")
            and (form.cleaned_data.get("image") or form.instance.image)
        ]
        new_photos = getattr(product, "_new_photo_count", 0)
        problems = publish_blockers(
            PublishCheck(
                has_category=product.category_id is not None,
                name_ka=product.name_ka or "",
                price=product.price,
                image_count=len(kept) + new_photos,
                images_missing_alt=sum(
                    1 for f in kept if not (f.cleaned_data.get("alt_ka") or "").strip()
                ),
            )
        )
        if problems:
            raise forms.ValidationError([gettext("This product can't be Active yet:"), *problems])


class ProductVariantFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        kept = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if sum(1 for f in kept if f.cleaned_data.get("is_default")) > 1:
            raise forms.ValidationError(gettext("Only one variant can be the default."))
        if self.instance.is_unique:
            if len(kept) > 1:
                raise forms.ValidationError(
                    gettext(
                        "A one-of-a-kind piece has a single variant. Uncheck “one of a kind” "
                        "to add more."
                    )
                )
            if any((f.cleaned_data.get("stock") or 0) > 1 for f in kept):
                raise forms.ValidationError(
                    gettext("A one-of-a-kind piece can't have more than 1 in stock.")
                )


class ProductImageInline(FormfieldDefaultsMixin, StackedInline, TranslationStackedInline):
    model = ProductImage
    formset = ProductImageFormSet
    extra = 0
    fields = ("preview", "image", "alt", "variant", "sort_order")
    readonly_fields = ("preview",)
    ordering_field = "sort_order"
    hide_ordering_field = True
    verbose_name = _("photo")
    verbose_name_plural = _("photos — drag to reorder; the first is the main photo")

    @display(description=_("preview"))
    def preview(self, obj: ProductImage):
        return _thumb_html(obj.image, 96)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "variant":
            object_id = request.resolver_match.kwargs.get("object_id")
            kwargs["queryset"] = ProductVariant.objects.filter(product_id=object_id or 0)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ProductVariantInline(FormfieldDefaultsMixin, StackedInline, TranslationStackedInline):
    model = ProductVariant
    formset = ProductVariantFormSet
    extra = 0
    fields = (
        ("name",),
        ("stock", "reserved"),
        ("price_override", "sku_suffix"),
        "is_default",
        "sort_order",
    )
    readonly_fields = ("reserved",)
    ordering_field = "sort_order"
    hide_ordering_field = True
    verbose_name = _("variant")
    verbose_name_plural = _("variants and stock")


# --- Product ----------------------------------------------------------------


@admin.register(Product)
class ProductAdmin(BaseModelAdmin, TabbedTranslationAdmin):
    form = ProductAdminForm
    inlines = (ProductImageInline, ProductVariantInline)
    # Three columns so a phone shows everything without sideways scrolling:
    # photo + name with "SKU · price" underneath, status, available stock.
    list_display = ("product", "status_label", "available_display")
    list_display_links = ("product",)
    list_filter = ("status", "category", "stones", "is_unique", "is_featured")
    search_fields = ("name_ka", "name_en", "sku")
    autocomplete_fields = ("category", "stones", "materials")
    list_select_related = ("category",)
    actions = ("make_visible", "make_hidden", "mark_as_sold", "duplicate")
    readonly_fields = ("created_at", "updated_at", "published_at", "sold_at")
    fieldsets = (
        (
            _("Basics"),
            {
                "fields": (
                    "name",
                    "category",
                    ("status", "price"),
                    "is_unique",
                    "is_preowned",
                    ("is_featured", "new_badge"),
                    "new_photos",
                )
            },
        ),
        (
            _("Story & details"),
            {
                "fields": (
                    "short_description",
                    "description",
                    "story",
                    "care_instructions",
                    "dimensions",
                    ("weight_g", "hours_to_make"),
                    "allow_commission_request",
                )
            },
        ),
        (_("Stones & materials"), {"fields": ("stones", "materials")}),
        (
            _("Search engines (SEO)"),
            {"classes": ("collapse",), "fields": ("slug", "seo_title", "seo_description")},
        ),
        (
            _("System"),
            {
                "classes": ("collapse",),
                "fields": ("sku", "created_at", "updated_at", "published_at", "sold_at"),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("images", "variants")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            fields.append("sku")  # never changes after creation
        return fields

    # --- list columns ---

    @display(description=_("product"), header=True, ordering="name")
    def product(self, obj: Product):
        image = obj.primary_image
        thumb = admin_thumb(image.image) if image else None
        picture = {"path": thumb.url, "squared": True, "width": 40, "height": 50} if thumb else None
        # Keep the SKU in one piece on narrow screens (it would break at its hyphens).
        subtitle = format_html(
            '<span style="white-space:nowrap">{}</span> · {}', obj.sku, format_gel(obj.price)
        )
        return [obj.name, subtitle, "", picture]

    @display(
        description=_("status"),
        ordering="status",
        label={
            Product.Status.ACTIVE: "success",
            Product.Status.DRAFT: "info",
            Product.Status.HIDDEN: "warning",
            Product.Status.SOLD: "danger",
        },
    )
    def status_label(self, obj: Product):
        return obj.status, obj.get_status_display()

    @display(description=_("available"))
    def available_display(self, obj: Product):
        return obj.total_available

    # --- saving ---

    def save_form(self, request, form, change):
        product = super().save_form(request, form, change)
        # Lets the photo formset count photos uploaded through "Add photos".
        product._new_photo_count = len(form.cleaned_data.get("new_photos") or [])
        return product

    def save_model(self, request, obj, form, change):
        # Runs only when the form and every inline are valid: no SKU is used up on errors.
        prepare_product_for_save(obj, is_new=not change)
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.model is not ProductImage:
            return super().save_formset(request, form, formset, change)
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        # By identity: unsaved model instances are not hashable.
        changed_files = [
            id(f.instance) for f in formset.forms if "image" in getattr(f, "changed_data", ())
        ]
        for image in instances:
            file_changed = id(image) in changed_files
            if file_changed and not self._process_image(request, image):
                continue
            image.save()
            if file_changed:
                self._queue_renditions(image)
        formset.save_m2m()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        self._add_new_photos(request, product, form.cleaned_data.get("new_photos") or [])
        ensure_default_variant(product)

    def _add_new_photos(self, request, product: Product, files) -> None:
        start = (product.images.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        for offset, upload in enumerate(files):
            image = ProductImage(
                product=product,
                sort_order=start + offset,
                alt_ka=product.name_ka,
                alt_en=product.name_en or "",
            )
            image.image = upload
            if self._process_image(request, image):
                image.save()
                self._queue_renditions(image)

    def _process_image(self, request, image: ProductImage) -> bool:
        try:
            processed = process_upload(image.image.file)
        except InvalidImageError:
            messages.error(
                request,
                gettext("“%(name)s” is not a readable image and was skipped.")
                % {"name": image.image.name},
            )
            return False
        image.image = processed.file
        if processed.below_recommended:
            messages.warning(
                request,
                gettext(
                    "A photo is %(w)s×%(h)s px — below the recommended 2000px; it may look "
                    "soft on large screens."
                )
                % {"w": processed.width, "h": processed.height},
            )
        return True

    @staticmethod
    def _queue_renditions(image: ProductImage) -> None:
        transaction.on_commit(lambda: generate_product_image_renditions(image.pk))

    # --- bulk actions ---

    @admin.action(description=_("Show in the shop"))
    def make_visible(self, request: HttpRequest, queryset):
        shown = 0
        for product in queryset:
            problems = set_visibility(product, True)
            if problems:
                messages.warning(
                    request, f"{product.sku} — {product.name_ka}: " + " ".join(problems)
                )
            else:
                shown += 1
        if shown:
            messages.success(
                request,
                ngettext("%d product is now visible.", "%d products are now visible.", shown)
                % shown,
            )

    @admin.action(description=_("Hide from the shop"))
    def make_hidden(self, request: HttpRequest, queryset):
        for product in queryset:
            set_visibility(product, False)
        messages.success(request, gettext("Selected products are hidden."))

    @admin.action(description=_("Mark as sold (move to archive)"))
    def mark_as_sold(self, request: HttpRequest, queryset):
        for product in queryset:
            try:
                inventory.mark_sold(product)
            except inventory.StockReservedError:
                messages.error(
                    request,
                    gettext("%(sku)s is reserved by an unpaid order and was not changed.")
                    % {"sku": product.sku},
                )
        messages.success(request, gettext("Selected products moved to the archive."))

    @admin.action(description=_("Duplicate as a new draft"))
    def duplicate(self, request: HttpRequest, queryset):
        copies = [duplicate_product(p) for p in queryset]
        if len(copies) == 1:
            url = reverse("admin:catalog_product_change", args=[copies[0].pk])
            messages.success(
                request,
                format_html(
                    '{} <a class="underline" href="{}">{}</a>',
                    gettext("Draft copy created:"),
                    url,
                    copies[0].sku,
                ),
            )
        else:
            messages.success(request, gettext("%d draft copies created.") % len(copies))


# --- Taxonomy ---------------------------------------------------------------


class SlugAutoFillMixin:
    def save_model(self, request, obj, form, change):
        fill_translated_slugs(obj)
        super().save_model(request, obj, form, change)


@admin.register(Category)
class CategoryAdmin(SlugAutoFillMixin, BaseModelAdmin, TabbedTranslationAdmin):
    list_display = ("name", "code", "parent", "is_active", "product_count")
    list_filter = ("is_active", "parent")
    search_fields = ("name_ka", "name_en", "code")
    ordering_field = "sort_order"
    hide_ordering_field = True
    fields = ("name", "code", "parent", "description", "image", "is_active", "slug")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products=Count("products"))

    @display(description=_("products"), ordering="_products")
    def product_count(self, obj):
        return obj._products

    def get_readonly_fields(self, request, obj=None):
        # The code prefixes existing SKUs; changing it later would confuse the owner.
        return ("code",) if obj and obj.products.exists() else ()


@admin.register(Stone)
class StoneAdmin(SlugAutoFillMixin, BaseModelAdmin, TabbedTranslationAdmin):
    list_display = ("swatch", "name", "product_count")
    list_display_links = ("swatch", "name")
    search_fields = ("name_ka", "name_en")
    ordering_field = "sort_order"
    hide_ordering_field = True
    fields = ("name", "short_description", "story", "color_hex", "image", "slug")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products=Count("products"))

    @display(description="")
    def swatch(self, obj: Stone):
        return format_html(
            '<span style="display:inline-block;width:20px;height:20px;border-radius:50%;'
            'background:{};border:1px solid rgba(0,0,0,.1)"></span>',
            obj.color_hex or "transparent",
        )

    @display(description=_("products"), ordering="_products")
    def product_count(self, obj):
        return obj._products


@admin.register(Material)
class MaterialAdmin(BaseModelAdmin, TabbedTranslationAdmin):
    list_display = ("name",)
    search_fields = ("name_ka", "name_en")
    ordering_field = "sort_order"
    hide_ordering_field = True
    fields = ("name",)
