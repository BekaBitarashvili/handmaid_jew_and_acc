"""Money helpers. Amounts are stored as integer tetri (1 GEL = 100 tetri); never floats."""

from decimal import Decimal

from django.utils.translation import get_language

TETRI_PER_GEL = 100
NBSP = " "
GEL_SIGN = "₾"  # ₾


def tetri_to_gel(tetri: int) -> Decimal:
    """14550 -> Decimal('145.50'). Used e.g. for payment provider APIs."""
    if not isinstance(tetri, int) or isinstance(tetri, bool):
        raise TypeError(f"tetri must be int, got {type(tetri).__name__}")
    return (Decimal(tetri) / TETRI_PER_GEL).quantize(Decimal("0.01"))


def gel_to_tetri(amount: Decimal | str | int) -> int:
    """Decimal('145.5') -> 14550. Rejects floats and sub-tetri precision."""
    if isinstance(amount, float):
        raise TypeError("Use Decimal or str for money, never float.")
    value = Decimal(str(amount)) * TETRI_PER_GEL
    if value != value.to_integral_value():
        raise ValueError(f"{amount} GEL has more than 2 decimal places")
    return int(value)


def format_gel(tetri: int, language: str | None = None) -> str:
    """Display format (SPEC §9.3): number then ₾, e.g. `145 ₾`, `1 250 ₾`.

    Whole amounts show no decimals. Thousands are grouped with a no-break
    space; the decimal separator is `,` in Georgian and `.` in English.
    A no-break space joins number and sign so they never wrap apart.
    """
    language = (language or get_language() or "ka")[:2]
    sign = "-" if tetri < 0 else ""
    lari, rest = divmod(abs(tetri), TETRI_PER_GEL)
    number = f"{lari:,}".replace(",", NBSP)
    if rest:
        decimal_sep = "," if language == "ka" else "."
        number = f"{number}{decimal_sep}{rest:02d}"
    return f"{sign}{number}{NBSP}{GEL_SIGN}"
