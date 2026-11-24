"""Generate favicon.ico and apple-touch-icon.png from static/brand/favicon.svg.

The SVG is the single source of the site icon. To switch to the real logo:
replace static/brand/favicon.svg (square, opaque background), then run
    uv run python scripts/build_favicons.py
and commit the three files in static/brand/.
"""

import io
from pathlib import Path

import resvg_py
from PIL import Image

BRAND = Path(__file__).resolve().parent.parent / "static" / "brand"
SOURCE = BRAND / "favicon.svg"
ICO_SIZES = (16, 32, 48)
APPLE_TOUCH_SIZE = 180

# resvg ignores the SVG's own `@media (max-width: 24px)` rule, so apply the same
# simplification explicitly for tab-sized renders.
SMALL_SIZE = 24
SMALL_SIZE_CSS = ".facets { display: none; } .outline { stroke-width: 2; }"


def render(size: int) -> Image.Image:
    # Render each size from the vector separately: sharper than downscaling one bitmap.
    png = resvg_py.svg_to_bytes(
        svg_path=str(SOURCE),
        width=size,
        height=size,
        style_sheet=SMALL_SIZE_CSS if size <= SMALL_SIZE else None,
    )
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


def main() -> None:
    frames = [render(size) for size in ICO_SIZES]
    ico = BRAND / "favicon.ico"
    frames[-1].save(ico, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=frames[:-1])

    apple = BRAND / "apple-touch-icon.png"
    # iOS needs an opaque image; it rounds the corners itself.
    render(APPLE_TOUCH_SIZE).convert("RGB").save(apple, format="PNG", optimize=True)

    for path in (ico, apple):
        print(f"{path.relative_to(BRAND.parent.parent)}  {path.stat().st_size / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
