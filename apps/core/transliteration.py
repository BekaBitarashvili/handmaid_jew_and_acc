"""Georgian -> Latin transliteration for URL slugs (SPEC §3), e.g. "ქარვა" -> "karva".

Based on the Georgian national romanization system (2002), without the
apostrophes it uses for ejective consonants, since slugs drop them anyway.
"""

from django.utils.text import slugify

MKHEDRULI_TO_LATIN = {
    "ა": "a",
    "ბ": "b",
    "გ": "g",
    "დ": "d",
    "ე": "e",
    "ვ": "v",
    "ზ": "z",
    "თ": "t",
    "ი": "i",
    "კ": "k",
    "ლ": "l",
    "მ": "m",
    "ნ": "n",
    "ო": "o",
    "პ": "p",
    "ჟ": "zh",
    "რ": "r",
    "ს": "s",
    "ტ": "t",
    "უ": "u",
    "ფ": "p",
    "ქ": "k",
    "ღ": "gh",
    "ყ": "q",
    "შ": "sh",
    "ჩ": "ch",
    "ც": "ts",
    "ძ": "dz",
    "წ": "ts",
    "ჭ": "ch",
    "ხ": "kh",
    "ჯ": "j",
    "ჰ": "h",
}

# Mtavruli capitals (U+1C90..U+1CBA) mirror Mkhedruli (U+10D0..U+10FA).
_MTAVRULI_OFFSET = 0x1C90 - 0x10D0
_TABLE = {ord(ch): latin for ch, latin in MKHEDRULI_TO_LATIN.items()}
_TABLE.update({ord(ch) + _MTAVRULI_OFFSET: latin for ch, latin in MKHEDRULI_TO_LATIN.items()})


def transliterate(text: str) -> str:
    """Replace Georgian letters with Latin; leave everything else unchanged."""
    return text.translate(_TABLE)


def slugify_ka(text: str) -> str:
    """Latin ASCII slug for Georgian (or mixed) text: "ხელნაკეთი ქარვა" -> "khelnaketi-karva"."""
    return slugify(transliterate(text))
