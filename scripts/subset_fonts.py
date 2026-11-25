"""Build the self-hosted woff2 fonts in static/fonts/ (SPEC §9.3).

Run only when changing fonts; the output is committed:
    uv run python scripts/subset_fonts.py

Sources are pinned to upstream commits. Each family is split into a Latin and/or
a Georgian subset so the browser (via `unicode-range`) only downloads the script
a page actually uses. Variable fonts are limited to the weights we use (300-500).
"""

import hashlib
import io
import shutil
import tempfile
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "fonts"

GOOGLE = "https://raw.githubusercontent.com/google/fonts"
CORMORANT_SHA = "3dd78844021e948ceb633d1dcee3f7885561b5d9"
NOTO_GEORGIAN_SHA = "8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5"
FIRAGO = (
    "https://raw.githubusercontent.com/bBoxType/FiraGO/5bbcb9d066ab563686ed1de1e6f62eec0148e82d"
)

# Keep in sync with the `unicode-range` values in assets/css/fonts.css.
LATIN = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
    "U+2000-206F,U+20AC,U+20BE,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
)
GEORGIAN = "U+0589,U+10A0-10FF,U+1C90-1CBF,U+2D00-2D2F"

FEATURES = ["kern", "liga", "calt", "ccmp", "locl", "mark", "mkmk", "tnum", "lnum", "pnum"]

# (output name, source url, axis limits for variable fonts, unicode ranges)
FONTS = [
    (
        "cormorant-garamond-latin",
        f"{GOOGLE}/{CORMORANT_SHA}/ofl/cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf",
        {"wght": (300, 500)},
        LATIN,
    ),
    (
        "cormorant-garamond-italic-latin",
        f"{GOOGLE}/{CORMORANT_SHA}/ofl/cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf",
        {"wght": (300, 500)},
        LATIN,
    ),
    (
        "noto-serif-georgian",
        f"{GOOGLE}/{NOTO_GEORGIAN_SHA}/ofl/notoserifgeorgian/NotoSerifGeorgian%5Bwdth,wght%5D.ttf",
        {"wdth": 100, "wght": (300, 500)},
        GEORGIAN,
    ),
    *(
        (
            f"firago-{weight}-{script}",
            f"{FIRAGO}/Fonts/FiraGO_TTF_1001/Roman/FiraGO-{style}.ttf",
            None,
            ranges,
        )
        for weight, style in ((300, "Light"), (400, "Regular"), (500, "Medium"))
        for script, ranges in (("latin", LATIN), ("georgian", GEORGIAN))
    ),
]

LICENSES = {
    "OFL-CormorantGaramond.txt": f"{GOOGLE}/{CORMORANT_SHA}/ofl/cormorantgaramond/OFL.txt",
    "OFL-NotoSerifGeorgian.txt": f"{GOOGLE}/{NOTO_GEORGIAN_SHA}/ofl/notoserifgeorgian/OFL.txt",
    "OFL-FiraGO.txt": f"{FIRAGO}/OFL.txt",
}


def fetch(url: str, cache: Path) -> bytes:
    path = cache / hashlib.sha256(url.encode()).hexdigest()  # several files share a name
    if not path.exists():
        print(f"  downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 (pinned https URL)
            path.write_bytes(response.read())
    return path.read_bytes()


def unicodes(ranges: str) -> list[int]:
    result: list[int] = []
    for part in ranges.split(","):
        start, _, end = part.removeprefix("U+").partition("-")
        result.extend(range(int(start, 16), int(end or start, 16) + 1))
    return result


def build(name: str, data: bytes, axes: dict | None, ranges: str) -> None:
    font = TTFont(io.BytesIO(data))
    options = subset.Options()
    options.layout_features = FEATURES
    options.name_IDs = ["*"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=unicodes(ranges))
    subsetter.subset(font)
    # Subset first, then limit axes: fontTools fails subsetting a just-instanced font.
    if axes:
        font = instancer.instantiateVariableFont(font, axes)
    target = OUT / f"{name}.woff2"
    font.flavor = "woff2"
    font.save(target)
    print(f"  {target.relative_to(ROOT)}  {target.stat().st_size / 1024:.1f} KiB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = Path(tempfile.gettempdir()) / "jewelry-font-sources"
    cache.mkdir(exist_ok=True)
    for name, url, axes, ranges in FONTS:
        build(name, fetch(url, cache), axes, ranges)
    for filename, url in LICENSES.items():
        (OUT / filename).write_bytes(fetch(url, cache))
    print("Done. Fonts are committed; re-run only when changing font sources.")


if __name__ == "__main__":
    main()
    shutil.rmtree(Path(tempfile.gettempdir()) / "jewelry-font-sources", ignore_errors=True)
