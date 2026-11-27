from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.decorators import display

from apps.core.admin_base import BaseModelAdmin

from .models import HeroSlide, Page


@admin.register(HeroSlide)
class HeroSlideAdmin(BaseModelAdmin, TabbedTranslationAdmin):
    list_display = ("preview", "title", "is_active")
    list_display_links = ("preview", "title")
    ordering_field = "sort_order"
    hide_ordering_field = True
    fieldsets = (
        (None, {"fields": ("title", "subtitle", "image", "image_mobile", "is_active")}),
        (
            _("Buttons"),
            {"fields": (("primary_text", "primary_link"), ("secondary_text", "secondary_link"))},
        ),
    )

    @display(description="")
    def preview(self, obj: HeroSlide):
        if not obj.image:
            return ""
        return format_html(
            '<img src="{}" alt="" style="width:96px;height:42px;object-fit:cover">', obj.image.url
        )


@admin.register(Page)
class PageAdmin(BaseModelAdmin, TabbedTranslationAdmin):
    """Terms and Privacy exist from the start (checkout links to them); the owner pastes the
    lawyer-approved text. They can't be added or deleted here."""

    list_display = ("title", "key", "has_text", "updated_at")
    fields = ("title", "body")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("text"), boolean=True)
    def has_text(self, obj: Page):
        return not obj.is_placeholder
