from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .admin_base import BaseModelAdmin
from .models import SiteSettings

# Re-register auth models with unfold styling.
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(DjangoUserAdmin, BaseModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin, BaseModelAdmin):
    pass


@admin.register(SiteSettings)
class SiteSettingsAdmin(BaseModelAdmin, TabbedTranslationAdmin):
    fieldsets = (
        (_("Brand"), {"fields": ("brand_name", "logo", "announcement_bar")}),
        (
            _("Contact"),
            {"fields": ("contact_phone", "contact_email", "contact_address")},
        ),
        (
            _("Social"),
            {"fields": ("instagram_url", "pinterest_url", "facebook_url", "tiktok_url")},
        ),
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
