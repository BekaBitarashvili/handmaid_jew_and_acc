"""Normalise uploaded product photos before they are stored.

- applies the phone's EXIF rotation, then drops ALL metadata (incl. GPS location)
- converts to RGB JPEG on ivory (no transparency), long side capped at 2400px
- reports photos below the 2000px guideline (SPEC §9.7) as a warning, never an error
"""

import io
from dataclasses import dataclass
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.utils.text import slugify
from PIL import Image, ImageOps

MAX_LONG_SIDE = 2400
RECOMMENDED_LONG_SIDE = 2000
JPEG_QUALITY = 90
IVORY = (250, 246, 239)


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedImage:
    file: ContentFile
    width: int
    height: int
    below_recommended: bool


def process_upload(upload: UploadedFile) -> ProcessedImage:
    try:
        upload.seek(0)
        with Image.open(upload) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise InvalidImageError(str(error)) from error

    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, IVORY)
        background.paste(image, mask=image.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    original_long_side = max(image.size)
    image.thumbnail((MAX_LONG_SIDE, MAX_LONG_SIDE), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    # No `exif=` argument: Pillow writes no metadata at all.
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    name = (slugify(Path(upload.name or "photo").stem) or "photo")[:60] + ".jpg"
    return ProcessedImage(
        file=ContentFile(buffer.getvalue(), name=name),
        width=image.width,
        height=image.height,
        below_recommended=original_long_side < RECOMMENDED_LONG_SIDE,
    )
