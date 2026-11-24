import io
import itertools
import string

import factory
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.models import Category, Material, Product, ProductImage, ProductVariant, Stone
from apps.catalog.services.products import ensure_default_variant, prepare_product_for_save

_codes = ("".join(c) for c in itertools.product(string.ascii_uppercase, repeat=3))


def make_jpeg(size=(800, 1000), color=(176, 141, 87), *, exif=None, mode="RGB", name="photo.jpg"):
    image = Image.new(mode, size, color if mode == "RGB" else (*color, 128))
    buffer = io.BytesIO()
    fmt = "PNG" if mode == "RGBA" else "JPEG"
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(buffer, format=fmt, **kwargs)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    code = factory.LazyFunction(lambda: next(_codes))
    name_ka = factory.Sequence(lambda n: f"კატეგორია {n}")
    name_en = factory.Sequence(lambda n: f"Category {n}")
    slug_ka = factory.Sequence(lambda n: f"kategoria-{n}")
    slug_en = factory.Sequence(lambda n: f"category-{n}")


class StoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Stone

    name_ka = factory.Sequence(lambda n: f"ქვა {n}")
    name_en = factory.Sequence(lambda n: f"Stone {n}")
    slug_ka = factory.Sequence(lambda n: f"kva-{n}")
    slug_en = factory.Sequence(lambda n: f"stone-{n}")
    color_hex = "#C8862A"


class MaterialFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Material

    name_ka = factory.Sequence(lambda n: f"მასალა {n}")
    name_en = factory.Sequence(lambda n: f"Material {n}")


class ProductFactory(factory.django.DjangoModelFactory):
    """Saved through the same service the admin uses (SKU, slugs, default variant)."""

    class Meta:
        model = Product
        skip_postgeneration_save = True

    category = factory.SubFactory(CategoryFactory)
    name_ka = factory.Sequence(lambda n: f"ქარვის ყელსაბამი {n}")
    name_en = factory.Sequence(lambda n: f"Amber necklace {n}")
    price = 14500
    status = Product.Status.DRAFT

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        product = model_class(*args, **kwargs)
        prepare_product_for_save(product, is_new=True)
        product.save()
        ensure_default_variant(product)
        return product


class ProductImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image = factory.LazyFunction(make_jpeg)
    alt_ka = "ფოტო"
    alt_en = "photo"
    sort_order = factory.Sequence(lambda n: n)


class ProductVariantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductVariant

    product = factory.SubFactory(ProductFactory, is_unique=False)
    name_ka = factory.Sequence(lambda n: f"ვარიანტი {n}")
    name_en = factory.Sequence(lambda n: f"Variant {n}")
    stock = 3
