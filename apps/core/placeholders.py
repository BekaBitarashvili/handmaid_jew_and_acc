"""Warm-toned placeholder images for the dev seed (never real or reference photos).

Soft gradients, a little grain and simple line drawings in the linen / clay / umber
palette, so the redesign can be judged before the owner's photography exists.
"""

import io
import math
import random

from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFilter

LINEN = (239, 229, 219)
OAT = (210, 192, 178)
CLAY = (164, 140, 122)
UMBER = (36, 20, 11)
ESPRESSO = (42, 26, 15)


def _hex(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient(size, top, bottom, *, diagonal=False) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    steps = width + height if diagonal else height
    for i in range(steps):
        color = _mix(top, bottom, i / max(steps - 1, 1))
        if diagonal:
            draw.line([(i, 0), (0, i)], fill=color, width=2)
        else:
            draw.line([(0, i), (width, i)], fill=color)
    return image


def _grain(image: Image.Image, amount: int = 10, seed: int = 0) -> Image.Image:
    rng = random.Random(seed)
    small = (max(image.width // 4, 1), max(image.height // 4, 1))
    noise = Image.new("L", small)
    noise.putdata([128 + rng.randint(-amount, amount) for _ in range(small[0] * small[1])])
    noise = noise.resize(image.size, Image.Resampling.NEAREST)
    return Image.composite(image, image.point(lambda v: max(v - 12, 0)), noise.point(lambda v: v))


def _soft_light(image: Image.Image, centre, radius, color, strength=0.55) -> Image.Image:
    glow = Image.new("RGB", image.size, color)
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse(
        [centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius],
        fill=round(255 * strength),
    )
    mask = mask.filter(ImageFilter.GaussianBlur(radius / 2))
    return Image.composite(glow, image, mask)


def _jpeg(image: Image.Image, name: str) -> ContentFile:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=86, optimize=True)
    return ContentFile(buffer.getvalue(), name=name)


def product_photo(stone_hex: str, seed: int, name: str) -> ContentFile:
    """Square: a faceted gem in the stone's colour resting on a warm stone surface."""
    size = 1600
    stone = _hex(stone_hex)
    base = _gradient((size, size), _mix(LINEN, OAT, 0.35), _mix(OAT, CLAY, 0.45), diagonal=True)
    base = _soft_light(base, (size * 0.35, size * 0.3), size * 0.45, LINEN, 0.5)
    draw = ImageDraw.Draw(base)
    # Soft shadow under the gem.
    shadow = Image.new("L", base.size, 0)
    ImageDraw.Draw(shadow).ellipse([520, 1090, 1080, 1180], fill=110)
    shadow = shadow.filter(ImageFilter.GaussianBlur(40))
    base = Image.composite(Image.new("RGB", base.size, _mix(CLAY, UMBER, 0.4)), base, shadow)
    draw = ImageDraw.Draw(base)
    cx, cy, r = size // 2, size // 2 - 60, 330 + (seed % 3) * 25
    rotation = (seed % 5 - 2) * 0.08
    points = []
    for angle, scale in ((-90, 1.0), (-20, 0.95), (90, 1.15), (200, 0.95)):
        a = math.radians(angle) + rotation
        points.append((cx + math.cos(a) * r * scale, cy + math.sin(a) * r * scale))
    draw.polygon(points, fill=_mix(stone, LINEN, 0.08))
    draw.polygon(points[:2] + [(cx, cy)] + points[3:], fill=_mix(stone, LINEN, 0.3))
    draw.line(points + [points[0]], fill=_mix(stone, UMBER, 0.45), width=5)
    draw.line([points[0], (cx, cy), points[2]], fill=_mix(stone, UMBER, 0.3), width=3)
    return _jpeg(_grain(base, 8, seed), name)


CATEGORY_DRAWINGS = ("necklace", "earring", "bracelet", "scarf", "brooch")


def category_tile(kind: str, seed: int, name: str) -> ContentFile:
    """Square warm tone with a thin-line drawing of the category."""
    size = 1600
    tones = [(196, 168, 146), (176, 146, 122), (210, 186, 166), (160, 132, 110), (188, 160, 140)]
    tone = tones[seed % len(tones)]
    base = _gradient((size, size), _mix(tone, LINEN, 0.25), _mix(tone, UMBER, 0.25))
    base = _soft_light(base, (size * 0.7, size * 0.25), size * 0.5, LINEN, 0.35)
    draw = ImageDraw.Draw(base)
    line = _mix(LINEN, OAT, 0.2)
    w = 7
    if kind == "necklace":
        draw.arc([360, 200, 1240, 1100], 20, 160, fill=line, width=w)
        draw.ellipse([760, 1010, 840, 1110], outline=line, width=w)
    elif kind == "earring":
        for x in (600, 1000):
            draw.line([(x, 420), (x, 640)], fill=line, width=w)
            draw.ellipse([x - 70, 640, x + 70, 820], outline=line, width=w)
    elif kind == "bracelet":
        draw.ellipse([420, 420, 1180, 1180], outline=line, width=w)
        for i in range(12):
            a = math.radians(i * 30)
            x, y = 800 + math.cos(a) * 380, 800 + math.sin(a) * 380
            draw.ellipse([x - 34, y - 34, x + 34, y + 34], outline=line, width=w - 2)
    elif kind == "scarf":
        draw.polygon([(400, 520), (1200, 520), (800, 1180)], outline=line, width=w)
        for i in range(1, 6):
            y = 520 + i * 110
            half = 400 - i * 66
            draw.line([(800 - half, y), (800 + half, y)], fill=line, width=3)
    else:
        draw.ellipse([560, 560, 1040, 1040], outline=line, width=w)
        draw.ellipse([700, 700, 900, 900], outline=line, width=w)
    return _jpeg(_grain(base, 8, seed), name)


def hero_image(seed: int, name: str) -> ContentFile:
    """Wide (2400x1050) umber -> clay gradient with soft out-of-focus light."""
    width, height = 2400, 1050
    palettes = [
        ((58, 36, 24), (156, 124, 100)),
        ((44, 28, 18), (190, 160, 132)),
        ((70, 46, 30), (140, 108, 84)),
    ]
    left, right = palettes[seed % len(palettes)]
    base = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(base)
    for x in range(width):
        draw.line([(x, 0), (x, height)], fill=_mix(left, right, x / (width - 1)))
    rng = random.Random(seed)
    for _ in range(9):
        cx = rng.randint(width // 2, width)
        cy = rng.randint(0, height)
        base = _soft_light(base, (cx, cy), rng.randint(90, 260), LINEN, rng.uniform(0.15, 0.4))
    return _jpeg(_grain(base, 10, seed), name)


def banner_image(name: str) -> ContentFile:
    """Dark umber drape-like texture for the Special Offers banner."""
    width, height = 2400, 900
    base = _gradient((width, height), (52, 32, 20), UMBER)
    draw = ImageDraw.Draw(base)
    for i in range(14):
        y = 60 + i * 64
        draw.arc([-400, y, width + 400, y + 700], 190, 350, fill=(70 + i, 44, 28), width=18)
    base = base.filter(ImageFilter.GaussianBlur(14))
    base = _soft_light(base, (360, 520), 300, OAT, 0.3)
    return _jpeg(_grain(base, 8, 3), name)
