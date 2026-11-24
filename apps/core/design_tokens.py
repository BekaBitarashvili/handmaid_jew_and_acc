"""Read the color tokens from assets/css/main.css and compute WCAG contrast.

Single source for the styleguide page and the token tests; the CSS stays the
source of truth for the values.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from django.conf import settings

MAIN_CSS = Path(settings.BASE_DIR) / "assets" / "css" / "main.css"

SURFACES = ("ivory", "cream", "sand")
TEXT = ("espresso", "cocoa", "taupe-text", "gold-text", "sold-text", "error")
DECORATIVE = ("taupe", "gold", "sold")

_TOKEN_RE = re.compile(r"--color-([a-z-]+):\s*(#[0-9a-fA-F]{6});\s*(?:/\*\s*(.*?)\s*\*/)?")


@dataclass(frozen=True)
class ColorToken:
    name: str
    hex: str
    note: str

    @property
    def css_var(self) -> str:
        return f"--color-{self.name}"


@cache
def color_tokens() -> dict[str, ColorToken]:
    css = MAIN_CSS.read_text(encoding="utf-8")
    return {
        m[1]: ColorToken(name=m[1], hex=m[2].upper(), note=(m[3] or "").strip())
        for m in _TOKEN_RE.finditer(css)
    }


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)
