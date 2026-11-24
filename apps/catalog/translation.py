from modeltranslation.translator import TranslationOptions, register

from .models import Category, Material, Product, ProductImage, ProductVariant, Stone


@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ("name", "slug", "description")


@register(Stone)
class StoneTranslationOptions(TranslationOptions):
    fields = ("name", "slug", "short_description", "story")


@register(Material)
class MaterialTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = (
        "name",
        "slug",
        "short_description",
        "description",
        "story",
        "care_instructions",
        "dimensions",
        "seo_title",
        "seo_description",
    )


@register(ProductVariant)
class ProductVariantTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ProductImage)
class ProductImageTranslationOptions(TranslationOptions):
    fields = ("alt",)
