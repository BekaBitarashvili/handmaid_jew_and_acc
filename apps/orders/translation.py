from modeltranslation.translator import TranslationOptions, register

from .models import DeliveryOption


@register(DeliveryOption)
class DeliveryOptionTranslationOptions(TranslationOptions):
    fields = ("name", "estimated_days")
