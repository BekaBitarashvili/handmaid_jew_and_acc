"""Guards SPEC §9.2: the linen palette's text colours pass WCAG AA where they are used."""

import re

import pytest

from apps.core.design_tokens import (
    DECORATIVE,
    FONTS_CSS,
    MAIN_CSS,
    SURFACES,
    TEXT,
    color_tokens,
    contrast,
)

TOKENS = {name: token.hex for name, token in color_tokens().items()}
CSS = MAIN_CSS.read_text(encoding="utf-8")


@pytest.mark.parametrize("surface", ["linen", "shell"])
@pytest.mark.parametrize("token", TEXT)
def test_text_tokens_pass_aa_on_light_surfaces(token, surface):
    ratio = contrast(TOKENS[token], TOKENS[surface])
    assert ratio >= 4.5, f"{token} on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("token", DECORATIVE)
def test_decorative_tokens_are_not_text_colours(token):
    # If one ever passes AA it could be promoted; until then it stays out of text.
    assert contrast(TOKENS[token], TOKENS["linen"]) < 4.5


@pytest.mark.parametrize(
    ("text", "background"),
    [
        ("espresso", "oat"),  # light filled buttons ("Shop Now")
        ("linen", "umber"),  # Special Offers banner, hero scrim
        ("oat", "umber"),  # light button on the dark banner
        ("linen", "clay-text"),  # round "-30%" badge (darkened from the reference's 2.6:1)
    ],
)
def test_pairings_used_by_components(text, background):
    assert contrast(TOKENS[text], TOKENS[background]) >= 4.5


def test_only_brand_palette_is_defined():
    assert set(TOKENS) == {*SURFACES, *TEXT, *DECORATIVE}
    assert "--color-*: initial" in CSS


def test_no_pure_white_or_black():
    assert not {"#FFFFFF", "#000000"} & set(TOKENS.values())


def test_contrast_reference_values():
    assert contrast("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert contrast("#777777", "#777777") == pytest.approx(1.0)


class TestItalicAndGeorgian:
    def test_latin_headings_are_italic_georgian_upright(self):
        block = CSS[CSS.index("  .italic-serif {") :][:200]
        assert "font-style: italic;" in block
        assert re.search(r"&:lang\(ka\) \{\s*font-style: normal;", block)

    def test_no_synthetic_italic_or_bold(self):
        assert "font-synthesis: none;" in CSS

    def test_italic_face_is_latin_only(self):
        fonts = FONTS_CSS.read_text(encoding="utf-8")
        italic = fonts[fonts.index("cormorant-garamond-italic-latin") - 200 :][:700]
        assert "font-style: italic;" in italic
        assert "10A0" not in italic  # no Georgian range in the italic face
        georgian = fonts[fonts.index('font-family: "Noto Serif Georgian"') :][:400]
        assert "italic" not in georgian


def test_georgian_size_adjust_is_read_from_fonts_css():
    from apps.core.design_tokens import georgian_size_adjust

    assert georgian_size_adjust() == 94


def test_small_georgian_text_is_lighter():
    label = CSS[CSS.index(".label {") :]
    label_ka = label[label.index("&:lang(ka)") : label.index("}", label.index("&:lang(ka)"))]
    assert "font-weight: 400" in label_ka
    assert "calc(var(--text-label) + 1px)" in label_ka
