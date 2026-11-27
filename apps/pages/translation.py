from modeltranslation.translator import TranslationOptions, register

from .models import HeroSlide, Page


@register(HeroSlide)
class HeroSlideTranslationOptions(TranslationOptions):
    fields = ("title", "subtitle", "primary_text", "secondary_text")


@register(Page)
class PageTranslationOptions(TranslationOptions):
    fields = ("title", "body")
