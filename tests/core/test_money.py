from decimal import Decimal

import pytest

from apps.core.money import format_gel, gel_to_tetri, tetri_to_gel

NBSP = " "


class TestConversion:
    def test_tetri_to_gel(self):
        assert tetri_to_gel(14550) == Decimal("145.50")
        assert tetri_to_gel(1) == Decimal("0.01")
        assert tetri_to_gel(0) == Decimal("0.00")

    def test_tetri_to_gel_rejects_non_int(self):
        with pytest.raises(TypeError):
            tetri_to_gel(145.5)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            tetri_to_gel(True)

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [(Decimal("145.5"), 14550), ("0.01", 1), (12, 1200), ("1250.00", 125000)],
    )
    def test_gel_to_tetri(self, amount, expected):
        assert gel_to_tetri(amount) == expected

    def test_gel_to_tetri_rejects_float(self):
        with pytest.raises(TypeError):
            gel_to_tetri(1.1)  # type: ignore[arg-type]

    def test_gel_to_tetri_rejects_sub_tetri(self):
        with pytest.raises(ValueError):
            gel_to_tetri("1.005")

    def test_round_trip(self):
        for tetri in (0, 1, 99, 100, 14550, 9_999_999):
            assert gel_to_tetri(tetri_to_gel(tetri)) == tetri


class TestFormat:
    def test_whole_amount_has_no_decimals(self):
        assert format_gel(14500, "en") == f"145{NBSP}₾"

    def test_thousands_grouped_with_nbsp(self):
        assert format_gel(125000, "ka") == f"1{NBSP}250{NBSP}₾"

    def test_decimal_separator_per_language(self):
        assert format_gel(14550, "ka") == f"145,50{NBSP}₾"
        assert format_gel(14505, "en") == f"145.05{NBSP}₾"

    def test_negative(self):
        assert format_gel(-2000, "en") == f"-20{NBSP}₾"

    def test_uses_active_language(self, ka):
        assert format_gel(150) == f"1,50{NBSP}₾"
