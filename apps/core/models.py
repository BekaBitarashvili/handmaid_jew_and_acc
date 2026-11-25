from django.db import models
from django.utils.translation import gettext_lazy as _

from .fields import MoneyField


class SiteSettings(models.Model):
    """Singleton holding shop-wide settings editable by the owner (SPEC §5 core)."""

    SINGLETON_PK = 1

    brand_name = models.CharField(_("brand name"), max_length=80, default="{{BRAND}}")
    logo = models.ImageField(
        _("logo"),
        upload_to="site/",
        blank=True,
        help_text=_("Optional. The brand name is shown as text when no logo is set."),
    )

    contact_phone = models.CharField(_("contact phone"), max_length=32, blank=True)
    contact_email = models.EmailField(_("contact email"), blank=True)
    contact_address = models.CharField(_("contact address"), max_length=255, blank=True)

    instagram_url = models.URLField(_("Instagram"), blank=True)
    facebook_url = models.URLField(_("Facebook"), blank=True)
    pinterest_url = models.URLField(_("Pinterest"), blank=True)
    tiktok_url = models.URLField(_("TikTok"), blank=True)

    legal_entity_name = models.CharField(_("legal entity name"), max_length=255, blank=True)
    legal_entity_id = models.CharField(_("legal entity ID"), max_length=32, blank=True)

    free_shipping_threshold = MoneyField(
        _("free shipping threshold (₾)"),
        null=True,
        blank=True,
        help_text=_("Order subtotal in lari. Empty means no free shipping."),
    )

    owner_notification_email = models.EmailField(_("owner notification email"), blank=True)
    owner_notification_phone = models.CharField(
        _("owner notification phone"), max_length=32, blank=True
    )

    announcement_bar = models.CharField(
        _("announcement bar"),
        max_length=200,
        blank=True,
        help_text=_("Optional one-line message at the top of every page."),
    )
    maintenance_mode = models.BooleanField(_("maintenance mode"), default=False)

    class Meta:
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")

    def __str__(self) -> str:
        return str(_("Site settings"))

    def save(self, *args, **kwargs) -> None:
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("SiteSettings is a singleton and cannot be deleted.")

    @classmethod
    def load(cls) -> "SiteSettings":
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
