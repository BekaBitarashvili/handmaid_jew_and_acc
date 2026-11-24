"""Guards SPEC §9.2: text color tokens must pass WCAG AA on both light surfaces."""

import re
from pathlib import Path

import pytest
from django.conf import settings

MAIN_CSS = Path(settings.BASE_DIR) / "assets" / "css" / "main.css"
TEXT_TOKENS = ["espresso", "cocoa", "taupe-text", "gold-text", "sold-text", "error"]
SURFACES = ["ivory", "cream"]
DECORATIVE = ["taupe", "gold", "sold"]


def _tokens() -> dict[str, str]:
    css = MAIN_CSS.read_text(encoding="utf-8")
    return {m[1]: m[2] for m in re.finditer(r"--color-([a-z-]+):\s*(#[0-9a-fA-F]{6})", css)}


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


TOKENS = _tokens()


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("token", TEXT_TOKENS)
def test_text_tokens_pass_aa(token, surface):
    ratio = contrast(TOKENS[token], TOKENS[surface])
    assert ratio >= 4.5, f"{token} on {surface} is {ratio:.2f}:1"


def test_ivory_on_espresso_passes_aa():
    assert contrast(TOKENS["ivory"], TOKENS["espresso"]) >= 4.5


def test_gold_on_espresso_footer_passes_aa():
    assert contrast(TOKENS["gold"], TOKENS["espresso"]) >= 4.5


def test_only_brand_palette_is_defined():
    assert set(TOKENS) == {*SURFACES, "sand", *TEXT_TOKENS, *DECORATIVE}
    assert "--color-*: initial" in MAIN_CSS.read_text(encoding="utf-8")


def test_no_pure_white_or_black():
    assert not {"#ffffff", "#000000"} & {v.lower() for v in TOKENS.values()}
