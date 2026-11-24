"""Model fields shared across apps."""

from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .money import TETRI_PER_GEL, gel_to_tetri, tetri_to_gel
from .sanitize import clean_html


class GelFormField(forms.DecimalField):
    """Owner types lari ("145" or "145.50"); the model stores integer tetri."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 9)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("min_value", Decimal("0"))
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, int) and not isinstance(value, bool):
            amount = tetri_to_gel(value)
            return amount.quantize(Decimal("1")) if value % TETRI_PER_GEL == 0 else amount
        return value

    def to_python(self, value):
        amount = super().to_python(value)
        if amount is None:
            return None
        try:
            return gel_to_tetri(amount)
        except (ValueError, InvalidOperation) as error:
            raise ValidationError(_("Use at most 2 decimal places.")) from error

    def validate(self, value):
        # Validate the tetri integer, not the Decimal (min/max are in GEL).
        forms.Field.validate(self, value)

    def run_validators(self, value):
        if value is not None:
            super().run_validators(Decimal(value) / TETRI_PER_GEL)


class MoneyField(models.PositiveIntegerField):
    """Amount in tetri (1 GEL = 100). Never a float. Edited in GEL in forms."""

    def formfield(self, **kwargs):
        # Callers (BaseModelAdmin) may pass a decimal widget; never an integer one,
        # which would reject "145.50" in the browser.
        return super().formfield(**{**kwargs, "form_class": GelFormField})


class RichTextField(models.TextField):
    """HTML from the admin editor, sanitised on every save (any write path)."""

    def pre_save(self, model_instance, add):
        value = clean_html(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, value)
        return value
