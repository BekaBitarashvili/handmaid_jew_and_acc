from django import forms
from django.contrib import admin
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.decorators import display

from apps.catalog.models import Product
from apps.core.admin_base import BaseModelAdmin
from apps.core.money import format_gel

from .models import Sale


class SaleAdminForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = "__all__"  # noqa: DJ007 (ModelAdmin narrows this to `fieldsets`)

    def clean(self):
        cleaned = super().clean()
        if not (
            cleaned.get("applies_to_all") or cleaned.get("products") or cleaned.get("categories")
        ):
            raise forms.ValidationError(
                gettext("Choose what the sale applies to: the whole shop, categories or products.")
            )
        return cleaned


class StatusFilter(admin.SimpleListFilter):
    title = _("status")
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return [
            ("running", _("Running")),
            ("scheduled", _("Scheduled")),
            ("ended", _("Ended")),
            ("off", _("Switched off")),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "running":
            return queryset.running(now)
        if self.value() == "scheduled":
            return queryset.filter(is_active=True, starts_at__gt=now)
        if self.value() == "ended":
            return queryset.filter(is_active=True, ends_at__lte=now)
        if self.value() == "off":
            return queryset.filter(is_active=False)
        return queryset


@admin.register(Sale)
class SaleAdmin(BaseModelAdmin, TabbedTranslationAdmin):
    form = SaleAdminForm
    list_display = ("name", "discount", "status_label", "starts_at", "ends_at", "affected")
    list_filter = (StatusFilter, "show_on_home")
    search_fields = ("name",)
    autocomplete_fields = ("products", "categories")
    fieldsets = (
        (_("Discount"), {"fields": ("name", "discount_type", ("percent", "amount"))}),
        (_("Applies to"), {"fields": ("applies_to_all", "categories", "products")}),
        (_("Period"), {"fields": (("starts_at", "ends_at"), "is_active")}),
        (
            _("Home page banner"),
            {"fields": ("show_on_home", "banner_title", "banner_subtitle", "banner_image")},
        ),
    )

    @display(description=_("discount"))
    def discount(self, obj: Sale):
        if obj.discount_type == Sale.DiscountType.PERCENT:
            return f"−{obj.percent}%"
        return f"−{format_gel(obj.amount or 0)}"

    @display(
        description=_("status"),
        label={"running": "success", "scheduled": "info", "ended": "warning", "off": "danger"},
    )
    def status_label(self, obj: Sale):
        now = timezone.now()
        if not obj.is_active:
            return "off", gettext("Switched off")
        if obj.starts_at > now:
            return "scheduled", gettext("Scheduled")
        if obj.ends_at and obj.ends_at <= now:
            return "ended", gettext("Ended")
        return "running", gettext("Running")

    @display(description=_("products"))
    def affected(self, obj: Sale) -> int:
        """How many listed products this sale covers (a quick sanity check for the owner)."""
        qs = Product.objects.filter(status=Product.Status.ACTIVE)
        if obj.applies_to_all:
            return qs.count()
        categories = list(obj.categories.values_list("pk", flat=True))
        return (
            qs.filter(
                Q(pk__in=obj.products.values("pk"))
                | Q(category_id__in=categories)
                | Q(category__parent_id__in=categories)
            )
            .distinct()
            .count()
        )
