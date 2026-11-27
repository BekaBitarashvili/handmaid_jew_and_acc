"""Phone numbers: parsed with `phonenumbers`, stored in E.164 (+995555123456).

Buyers may live anywhere (default region Georgia, so "555 12 34 56" works); the gift
recipient must have a Georgian number, since delivery is Georgia only. Mobile and
landline numbers are both accepted.
"""

import phonenumbers
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

DEFAULT_REGION = "GE"
GEORGIA = 995


def normalize_phone(raw: str, *, georgian_only: bool = False) -> str:
    """E.164 string, or ValidationError with a message for the customer."""
    try:
        number = phonenumbers.parse((raw or "").strip(), DEFAULT_REGION)
    except phonenumbers.NumberParseException as error:
        raise ValidationError(_("Enter a valid phone number."), code="invalid") from error
    if not phonenumbers.is_valid_number(number):
        raise ValidationError(_("Enter a valid phone number."), code="invalid")
    if georgian_only and number.country_code != GEORGIA:
        raise ValidationError(
            _("The recipient's number must be Georgian (+995)."), code="not_georgian"
        )
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def format_phone(e164: str) -> str:
    """Readable international form for pages, emails and the admin: +995 555 12 34 56."""
    if not e164:
        return ""
    try:
        number = phonenumbers.parse(e164, None)
    except phonenumbers.NumberParseException:
        return e164
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
