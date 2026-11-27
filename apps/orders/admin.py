from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.decorators import display

from apps.core.admin_base import BaseModelAdmin
from apps.core.money import format_gel

from .models import DeliveryOption


@admin.register(DeliveryOption)
class DeliveryOptionAdmin(BaseModelAdmin, TabbedTranslationAdmin):
    list_display = ("name", "price_display", "estimated_days", "free_over_threshold", "is_active")
    list_filter = ("is_active",)
    ordering_field = "sort_order"
    hide_ordering_field = True
    fields = (
        "name",
        "code",
        "price",
        "estimated_days",
        "requires_address",
        "free_over_threshold",
        "is_active",
    )

    @display(description=_("price"), ordering="price")
    def price_display(self, obj: DeliveryOption):
        return format_gel(obj.price)


from . import admin_orders  # noqa: E402, F401  (Order admin: list, detail, slip)
