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
        self.stdout.write(self.style.SUCCESS(f"Done: {total} photos."))
