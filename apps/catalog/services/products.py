"""Product lifecycle rules: SKU, slugs, default variant, publishing, duplication."""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.catalog.models import Category, Product, ProductImage, ProductVariant, SkuSequence

from .slugs import LANGUAGES, fill_translated_slugs


def next_sku(category: Category) -> str:
    """Next code for the category and current year, e.g. NEC-2026-0001.

    The counter row is locked, so two products saved at once never share a code.
    """
    year = timezone.localdate().year
    with transaction.atomic():
        SkuSequence.objects.get_or_create(prefix=category.code, year=year)
        sequence = SkuSequence.objects.select_for_update().get(prefix=category.code, year=year)
        sequence.last_number += 1
        sequence.save(update_fields=["last_number"])
    return f"{category.code}-{year}-{sequence.last_number:04d}"


def prepare_product_for_save(product: Product, *, is_new: bool) -> None:
    """Fill derived fields before saving. The SKU is assigned once, at creation."""
    if is_new and not product.sku:
        product.sku = next_sku(product.category)
    fill_translated_slugs(product)
    if product.status == Product.Status.ACTIVE and product.published_at is None:
        product.published_at = timezone.now()
    if product.status == Product.Status.SOLD:
        if product.sold_at is None:
            product.sold_at = timezone.now()
    else:
        product.sold_at = None  # back on sale (or hidden): not in the archive


def ensure_default_variant(product: Product) -> ProductVariant:
    """Every product sells through at least one variant; exactly one is the default."""
    variants = list(product.variants.order_by("sort_order", "pk"))
    if not variants:
        return ProductVariant.objects.create(
            product=product, is_default=True, stock=1 if product.is_unique else 0
        )
    defaults = [v for v in variants if v.is_default]
    if defaults:
        return defaults[0]
    first = variants[0]
    first.is_default = True
    first.save(update_fields=["is_default"])
    return first


@dataclass(frozen=True)
class PublishCheck:
    has_category: bool
    name_ka: str
    price: int | None
    image_count: int
    images_missing_alt: int


def publish_blockers(check: PublishCheck) -> list[str]:
    """Why a product cannot be Active yet (SPEC §10). Empty list = OK to publish."""
    problems = []
    if not check.name_ka.strip():
        problems.append(_("Add the Georgian name."))
    if not check.has_category:
        problems.append(_("Choose a category."))
    if not check.price:
        problems.append(_("Set a price above 0."))
    if check.image_count < 1:
        problems.append(_("Add at least one photo."))
    if check.images_missing_alt:
        problems.append(_("Every photo needs a Georgian description for screen readers."))
    return problems


def publish_blockers_for(product: Product) -> list[str]:
    """Publish check against what is stored in the database."""
    images = list(product.images.all())
    return publish_blockers(
        PublishCheck(
            has_category=product.category_id is not None,
            name_ka=product.name_ka or "",
            price=product.price,
            image_count=len(images),
            images_missing_alt=sum(1 for i in images if not (i.alt_ka or "").strip()),
        )
    )


TRANSLATED_FIELDS = (
    "name",
    "short_description",
    "description",
    "story",
    "care_instructions",
    "dimensions",
    "seo_title",
    "seo_description",
)


@transaction.atomic
def duplicate_product(product: Product) -> Product:
    """A new draft copy with its own SKU and slugs; variants and photos are copied too."""
    copy = Product(
        category=product.category,
        price=product.price,
        is_unique=product.is_unique,
        is_featured=False,
        new_badge=Product.NewBadge.AUTO,
        allow_commission_request=product.allow_commission_request,
        weight_g=product.weight_g,
        hours_to_make=product.hours_to_make,
        status=Product.Status.DRAFT,
    )
    for field in TRANSLATED_FIELDS:
        for lang in LANGUAGES:
            setattr(copy, f"{field}_{lang}", getattr(product, f"{field}_{lang}"))
    copy.slug_ka = f"{product.slug_ka}-copy"
    copy.slug_en = f"{product.slug_en}-copy"
    prepare_product_for_save(copy, is_new=True)
    copy.save()
    copy.stones.set(product.stones.all())
    copy.materials.set(product.materials.all())

    variant_map = {}
    for variant in product.variants.all():
        old_pk = variant.pk
        variant.pk = None
        variant.product = copy
        variant.reserved = 0
        variant.save()
        variant_map[old_pk] = variant
    for image in product.images.all():
        image.pk = None
        image.product = copy
        image.variant = variant_map.get(image.variant_id)
        image.save()
    ensure_default_variant(copy)
    return copy


def set_visibility(product: Product, visible: bool) -> list[str]:
    """Show (Active) or hide a product. Showing requires the publish checks to pass."""
    if visible:
        problems = publish_blockers_for(product)
        if problems:
            return problems
        product.status = Product.Status.ACTIVE
        if product.published_at is None:
            product.published_at = timezone.now()
    else:
        product.status = Product.Status.HIDDEN
    product.save(update_fields=["status", "published_at", "updated_at"])
    return []


def first_image(product: Product) -> ProductImage | None:
    return product.images.order_by("sort_order", "pk").first()
