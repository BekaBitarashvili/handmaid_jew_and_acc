from huey.contrib.djhuey import db_task

from .images import generate_all
from .models import ProductImage


@db_task(retries=2, retry_delay=30)
def generate_product_image_renditions(image_id: int) -> int:
    """Build the AVIF/WebP sizes for one photo so the first visitor doesn't wait."""
    image = ProductImage.objects.filter(pk=image_id).first()
    if image is None:  # deleted before the task ran
        return 0
    return generate_all(image.image)
