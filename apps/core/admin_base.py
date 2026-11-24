"""Admin building blocks shared by every app (import these, not unfold's classes directly)."""

from django.db import models
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.widgets import UnfoldAdminDecimalFieldWidget

from .fields import MoneyField, RichTextField


class FormfieldDefaultsMixin:
    """Project-wide widget choices for admins and inlines."""

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if isinstance(db_field, MoneyField):
            # Lari with up to 2 decimals; the field converts to tetri.
            kwargs["widget"] = UnfoldAdminDecimalFieldWidget(
                attrs={"step": "0.01", "inputmode": "decimal"}
            )
        elif isinstance(db_field, RichTextField):
            kwargs["widget"] = WysiwygWidget
        elif isinstance(db_field, models.URLField):
            # Owners type "instagram.com/…" — assume https (also Django 6.0's default).
            kwargs.setdefault("assume_scheme", "https")
        return super().formfield_for_dbfield(db_field, request, **kwargs)


class BaseModelAdmin(FormfieldDefaultsMixin, ModelAdmin):
    """Every app's ModelAdmin inherits from this."""

    # Phones: fewer rows per page, buttons stay reachable.
    list_per_page = 30
    warn_unsaved_form = True


class BaseTabularInline(FormfieldDefaultsMixin, TabularInline):
    pass


class BaseStackedInline(FormfieldDefaultsMixin, StackedInline):
    pass
