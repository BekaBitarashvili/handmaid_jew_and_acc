"""Responsive product image renditions (SPEC §5): 4:5 crops, AVIF + WebP.

easy-thumbnails picks its output format from a project-wide setting, so each
format gets its own thumbnailer with `thumbnail_extension` set per call.
"""

from dataclasses import dataclass

from easy_thumbnails.files import get_thumbnailer
from PIL import Image

WIDTHS = (400, 800, 1200, 1800)
FORMATS = ("avif", "webp")
QUALITY = {"avif": 60, "webp": 80}
ADMIN_THUMB = {"width": 96, "format": "webp"}


@dataclass(frozen=True)
class Rendition:
    url: str
    width: int
    height: int


def _options(width: int) -> dict:
    # 4:5 portrait, centre crop; never upscale small sources.
    return {"size": (width, width * 5 // 4), "crop": True, "upscale": False}


def rendition(image_field, width: int, fmt: str, *, generate: bool = True) -> Rendition | None:
    if not image_field:
        return None
    thumbnailer = get_thumbnailer(image_field)
    thumbnailer.thumbnail_extension = fmt
    thumbnailer.thumbnail_quality = QUALITY.get(fmt, 80)
    thumb = thumbnailer.get_thumbnail(_options(width), generate=generate)
    if thumb is None:
        return None
    return Rendition(url=thumb.url, width=thumb.width, height=thumb.height)


def srcset(image_field, fmt: str) -> str:
    """srcset value (url 400w, url 800w, …) for a <source type="image/avif|webp">."""
    parts = []
    for width in WIDTHS:
        r = rendition(image_field, width, fmt)
        if r:
            parts.append(f"{r.url} {r.width}w")
    return ", ".join(parts)


def generate_all(image_field) -> int:
    """Pre-build every rendition (run in the background after upload)."""
    count = 0
    for fmt in FORMATS:
        for width in WIDTHS:
            if rendition(image_field, width, fmt):
                count += 1
    if admin_thumb(image_field):
        count += 1
    return count


def admin_thumb(image_field) -> Rendition | None:
    return rendition(image_field, ADMIN_THUMB["width"], ADMIN_THUMB["format"])


# JPEG-style subsampling ints that easy-thumbnails always passes, as AVIF strings.
_AVIF_SUBSAMPLING = {0: "4:4:4", 1: "4:2:2", 2: "4:2:0"}


def install_avif_compat() -> None:
    """Make Pillow's AVIF encoder accept what easy-thumbnails sends.

    easy-thumbnails (2.10) passes `subsampling=2` (JPEG style; AVIF needs "4:2:0")
    and drops `quality` for every format except WebP. Wrap the AVIF save handler
    once so both arrive in a form the encoder understands. Called from
    CatalogConfig.ready(); idempotent.
    """
    Image.init()
    original = Image.SAVE.get("AVIF")
    if original is None or getattr(original, "_jewelry_compat", False):
        return

    def save(im, fp, filename):
        info = im.encoderinfo
        if isinstance(info.get("subsampling"), int):
            info["subsampling"] = _AVIF_SUBSAMPLING.get(info["subsampling"], "4:2:0")
        info.setdefault("quality", QUALITY["avif"])
        return original(im, fp, filename)

    save._jewelry_compat = True
    Image.register_save("AVIF", save)
