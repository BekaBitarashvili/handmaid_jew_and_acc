from modeltranslation.translator import TranslationOptions, register

from .models import Sale


@register(Sale)
class SaleTranslationOptions(TranslationOptions):
    fields = ("banner_title", "banner_subtitle")
