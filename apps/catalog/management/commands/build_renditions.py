"""Pre-build AVIF/WebP sizes for every product photo (e.g. after a deploy or import).

uv run python manage.py build_renditions
"""

from django.core.management.base import BaseCommand

from apps.catalog.images import generate_all, picture
from apps.catalog.models import ProductImage


class Command(BaseCommand):
    help = "Generate all responsive renditions for product photos and warm the picture cache."

    def handle(self, *args, **options):
        images = ProductImage.objects.order_by("pk")
        total = images.count()
        for index, image in enumerate(images.iterator(), start=1):
            built = generate_all(image.image)
            picture(image.image)  # warm the cache
            self.stdout.write(f"[{index}/{total}] {image.image.name}: {built} renditions")
        # Home page: hero slides (wide + phone crops), category tiles, sale banners.
        from apps.catalog.images import BANNER_WIDTHS, responsive
        from apps.catalog.models import Category
        from apps.pages.models import HeroSlide
        from apps.promotions.models import Sale

        for slide in HeroSlide.objects.all():
            responsive(slide.image, (16, 7))
            responsive(slide.image_mobile or slide.image, (4, 5), widths=(480, 768, 1080))
        for category in Category.objects.exclude(image=""):
            responsive(category.image, (1, 1), widths=BANNER_WIDTHS)
        for sale in Sale.objects.exclude(banner_image=""):
            responsive(sale.banner_image, (16, 5))
            responsive(sale.banner_image, (4, 5), widths=(480, 768, 1080))
        self.stdout.write(self.style.SUCCESS(f"Done: {total} photos + home page images."))
