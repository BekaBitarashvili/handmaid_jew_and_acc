from modeltranslation.translator import TranslationOptions, register

from .models import HeroSlide


@register(HeroSlide)
class HeroSlideTranslationOptions(TranslationOptions):
    fields = ("title", "subtitle", "primary_text", "secondary_text")
