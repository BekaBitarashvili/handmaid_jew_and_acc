from django.db import models
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from apps.core.fields import RichTextField

LINK_HELP = _(
    "A shop path such as /shop/new/ (the language is added automatically) or a full "
    "https:// address."
)


def localized_link(link: str) -> str:
    """ "/shop/new/" -> "/ka/shop/new/" for the active language; other links unchanged."""
    if not link or not link.startswith("/") or link.startswith(("/ka/", "/en/")):
        return link
    return f"/{(get_language() or 'ka')[:2]}{link}"


class HeroSlide(models.Model):
    """A slide of the home-page hero (redesign). Manual slider: no autoplay (SPEC §9.6)."""

    image = models.ImageField(
        _("photo"),
        upload_to="hero/",
        help_text=_("Wide photo, at least 2400px across. The text sits on its left side."),
    )
    image_mobile = models.ImageField(
        _("phone photo"),
        upload_to="hero/",
        blank=True,
        help_text=_("Optional portrait version for phones; otherwise the wide photo is cropped."),
    )
    title = models.CharField(_("title"), max_length=80)
    subtitle = models.CharField(_("subtitle"), max_length=160, blank=True)
    primary_text = models.CharField(_("first button text"), max_length=40, blank=True)
    primary_link = models.CharField(
        _("first button link"), max_length=200, blank=True, help_text=LINK_HELP
    )
    secondary_text = models.CharField(_("second button text"), max_length=40, blank=True)
    secondary_link = models.CharField(
        _("second button link"), max_length=200, blank=True, help_text=LINK_HELP
    )
    sort_order = models.PositiveIntegerField(_("order"), default=0, db_index=True)
    is_active = models.BooleanField(_("shown"), default=True)

    class Meta:
        verbose_name = _("hero slide")
        verbose_name_plural = _("hero slides")
        ordering = ("sort_order", "pk")

    def __str__(self) -> str:
        return self.title

    @property
    def primary_url(self) -> str:
        return localized_link(self.primary_link)

    @property
    def secondary_url(self) -> str:
        return localized_link(self.secondary_link)


class Page(models.Model):
    """Legal and info pages (SPEC §5 pages). The owner provides the text (with a lawyer for
    the legal ones); until then the page says so — no invented legal text."""

    class Key(models.TextChoices):
        TERMS = "terms", _("Terms and conditions")
        PRIVACY = "privacy", _("Privacy policy")

    key = models.CharField(_("page"), max_length=20, choices=Key.choices, unique=True)
    title = models.CharField(_("title"), max_length=150)
    body = RichTextField(_("text"), blank=True)
    is_legal = models.BooleanField(_("legal page"), default=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("page")
        verbose_name_plural = _("pages")
        ordering = ("key",)

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse(f"pages:{self.key}")

    @property
    def is_placeholder(self) -> bool:
        return not (self.body or "").strip()
