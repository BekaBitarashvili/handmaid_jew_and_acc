"""Georgian-safe `capfirst`.

Django capitalises the first letter of field labels, column headers and model
names (`django.utils.text.capfirst` and the `|capfirst` template filter). Since
Python 3.7 (Unicode 11), `"ე".upper()` returns the Mtavruli capital "Ე". Georgian
text does not start sentences or labels with Mtavruli, and our fonts (FiraGO)
have no Mtavruli glyphs, so every Georgian admin label would begin with a wrong,
fallback-font letter: "Ერთადერთი ეგზემპლარი" instead of "ერთადერთი ეგზემპლარი".

`install()` swaps in a version that leaves Georgian (Mkhedruli) untouched and
behaves exactly like Django's for everything else. Called from CoreConfig.ready().
"""

import sys

from django.template import defaultfilters
from django.utils import text as django_text
from django.utils.functional import keep_lazy_text

MKHEDRULI = range(0x10D0, 0x1100)  # ა … ჿ


def _is_georgian(char: str) -> bool:
    return ord(char) in MKHEDRULI


@keep_lazy_text
def capfirst(x):
    """Like django.utils.text.capfirst, but never turns Mkhedruli into Mtavruli."""
    if not x:
        return x
    if not isinstance(x, str):
        x = str(x)
    if _is_georgian(x[0]):
        return x
    return x[0].upper() + x[1:]


def _capfirst_filter(value):
    return capfirst(value) if value else value


_capfirst_filter.is_safe = True


def install() -> None:
    original = django_text.capfirst
    if original is capfirst:
        return
    django_text.capfirst = capfirst
    # Modules that did `from django.utils.text import capfirst` before this ran
    # (Django model fields, forms, admin helpers, unfold) hold the old function.
    for module in list(sys.modules.values()):
        if getattr(module, "capfirst", None) is original:
            module.capfirst = capfirst
    # The template filter is a separate function in defaultfilters.
    defaultfilters.register.filters["capfirst"] = defaultfilters.stringfilter(_capfirst_filter)
