"""Responsive product image renditions (SPEC §5): square 1:1 crops, AVIF + WebP.

easy-thumbnails picks its output format from a project-wide setting, so each
format gets its own thumbnailer with `thumbnail_extension` set per call.
"""

from dataclasses import asdict, dataclass

from django.core.cache import cache
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
    # Square, centre crop (redesign: 1:1 everywhere); never upscale small sources.
    return {"size": (width, width), "crop": True, "upscale": False}


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
    seen, parts = set(), []
    for width in WIDTHS:
        r = rendition(image_field, width, fmt)
        if r and r.width not in seen:  # small sources aren't upscaled: skip repeats
            seen.add(r.width)
            parts.append(f"{r.url} {r.width}w")
    return ", ".join(parts)


@dataclass(frozen=True)
class Picture:
    """Everything a <picture> element needs for one product photo."""

    avif_srcset: str
    webp_srcset: str
    src: str
    width: int
    height: int
    large_url: str  # 1800px WebP, for the fullscreen viewer and JSON-LD


PICTURE_CACHE_SECONDS = 60 * 60 * 24 * 30


def picture(image_field) -> Picture | None:
    """Cached <picture> data. easy-thumbnails checks its database once per size, so a
    product grid would cost ~8 queries per card without this. Uploaded files never
    change in place (a new upload gets a new name), so the file name is a safe key."""
    if not image_field:
        return None
    key = f"picture:v2:{image_field.name}"  # v2: square renditions
    cached = cache.get(key)
    if cached is not None:
        return Picture(**cached)
    fallback = rendition(image_field, 800, "webp")
    large = rendition(image_field, 1800, "webp")
    if fallback is None or large is None:
        return None
    result = Picture(
        avif_srcset=srcset(image_field, "avif"),
        webp_srcset=srcset(image_field, "webp"),
        src=fallback.url,
        width=fallback.width,
        height=fallback.height,
        large_url=large.url,
    )
    cache.set(key, asdict(result), PICTURE_CACHE_SECONDS)
    return result


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


@dataclass(frozen=True)
class Responsive:
    avif_srcset: str
    webp_srcset: str
    src: str
    width: int
    height: int


BANNER_WIDTHS = (800, 1280, 1920, 2560)


def responsive(image_field, ratio: tuple[int, int], widths=BANNER_WIDTHS) -> Responsive | None:
    """Cached AVIF + WebP srcsets for a centre crop of `image_field` at `ratio` (w, h)."""
    if not image_field:
        return None
    key = f"responsive:v1:{image_field.name}:{ratio[0]}x{ratio[1]}:{widths[-1]}"
    cached = cache.get(key)
    if cached is not None:
        return Responsive(**cached)
    sets: dict[str, list[str]] = {"avif": [], "webp": []}
    fallback = None
    for fmt in FORMATS:
        seen = set()
        for width in widths:
            thumbnailer = get_thumbnailer(image_field)
            thumbnailer.thumbnail_extension = fmt
            thumbnailer.thumbnail_quality = QUALITY[fmt]
            size = (width, round(width * ratio[1] / ratio[0]))
            thumb = thumbnailer.get_thumbnail({"size": size, "crop": True, "upscale": False})
            if thumb.width in seen:
                continue
            seen.add(thumb.width)
            sets[fmt].append(f"{thumb.url} {thumb.width}w")
            if fmt == "webp" and (fallback is None or thumb.width <= 1280):
                fallback = thumb
    result = Responsive(
        avif_srcset=", ".join(sets["avif"]),
        webp_srcset=", ".join(sets["webp"]),
        src=fallback.url,
        width=fallback.width,
        height=fallback.height,
    )
    cache.set(key, asdict(result), PICTURE_CACHE_SECONDS)
    return result
