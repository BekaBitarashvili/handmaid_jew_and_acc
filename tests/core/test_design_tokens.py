"""Guards SPEC §9.2: text color tokens must pass WCAG AA on both light surfaces."""

import pytest

from apps.core.design_tokens import DECORATIVE, MAIN_CSS, SURFACES, TEXT, color_tokens, contrast

TOKENS = {name: token.hex for name, token in color_tokens().items()}


@pytest.mark.parametrize("surface", ["ivory", "cream"])
@pytest.mark.parametrize("token", TEXT)
def test_text_tokens_pass_aa(token, surface):
    ratio = contrast(TOKENS[token], TOKENS[surface])
    assert ratio >= 4.5, f"{token} on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("token", DECORATIVE)
def test_decorative_tokens_are_documented_as_not_for_text(token):
    # If a decorative color ever passes AA it could be promoted; until then keep it out of text.
    assert contrast(TOKENS[token], TOKENS["ivory"]) < 4.5


def test_ivory_on_espresso_passes_aa():
    assert contrast(TOKENS["ivory"], TOKENS["espresso"]) >= 4.5


def test_gold_on_espresso_footer_passes_aa():
    assert contrast(TOKENS["gold"], TOKENS["espresso"]) >= 4.5


def test_only_brand_palette_is_defined():
    assert set(TOKENS) == {*SURFACES, *TEXT, *DECORATIVE}
    assert "--color-*: initial" in MAIN_CSS.read_text(encoding="utf-8")


def test_no_pure_white_or_black():
    assert not {"#FFFFFF", "#000000"} & set(TOKENS.values())


def test_contrast_reference_values():
    assert contrast("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert contrast("#777777", "#777777") == pytest.approx(1.0)
