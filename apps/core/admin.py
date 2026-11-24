from django.contrib import admin
from django.db import models
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin

from .models import SiteSettings


class BaseModelAdmin(ModelAdmin):
    """Project-wide admin base: every app's admin should inherit from this."""

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Owners type "instagram.com/…" — assume https (also Django 6.0's default).
        if isinstance(db_field, models.URLField):
            kwargs.setdefault("assume_scheme", "https")
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(SiteSettings)
class SiteSettingsAdmin(BaseModelAdmin, TabbedTranslationAdmin):
    fieldsets = (
        (_("Brand"), {"fields": ("brand_name", "logo", "announcement_bar")}),
        (
            _("Contact"),
            {"fields": ("contact_phone", "contact_email", "contact_address")},
        ),
        (_("Social"), {"fields": ("instagram_url", "facebook_url", "tiktok_url")}),
        (_("Legal entity"), {"fields": ("legal_entity_name", "legal_entity_id")}),
        (_("Shipping"), {"fields": ("free_shipping_threshold",)}),
        (
            _("Owner notifications"),
            {"fields": ("owner_notification_email", "owner_notification_phone")},
        ),
        (_("Maintenance"), {"fields": ("maintenance_mode",)}),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def changelist_view(self, request: HttpRequest, extra_context=None):
        # A singleton has no list: go straight to its edit form.
        obj = SiteSettings.load()
        return HttpResponseRedirect(reverse("admin:core_sitesettings_change", args=[obj.pk]))
