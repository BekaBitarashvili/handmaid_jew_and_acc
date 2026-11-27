from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.phones import normalize_phone

from .models import DeliveryOption, Order
from .services import CheckoutData

GIFT_NOTE_MAX = 300


class CheckoutForm(forms.Form):
    """Guest checkout (SPEC §6.4). Delivery is Georgia only: "Courier in Tbilisi" has no
    city field, the regions courier needs a city, pickup needs no address at all."""

    # Contact
    first_name = forms.CharField(label=_("First name"), max_length=100)
    last_name = forms.CharField(label=_("Last name"), max_length=100)
    email = forms.EmailField(label=_("Email"))
    phone = forms.CharField(
        label=_("Phone"),
        max_length=30,
        help_text=_("For delivery questions. Any country; Georgian numbers without +995 work too."),
    )

    # Delivery
    delivery = forms.ModelChoiceField(
        label=_("Delivery"),
        queryset=DeliveryOption.objects.filter(is_active=True),
        widget=forms.RadioSelect,
        empty_label=None,
    )
    city = forms.CharField(label=_("City or village"), max_length=100, required=False)
    address_line = forms.CharField(label=_("Address"), max_length=255, required=False)
    delivery_notes = forms.CharField(
        label=_("Notes for delivery"),
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Entrance, floor, the best time to reach you."),
    )
    recipient_name = forms.CharField(label=_("Recipient name"), max_length=150, required=False)
    recipient_phone = forms.CharField(
        label=_("Recipient phone"),
        max_length=30,
        required=False,
        help_text=_("A Georgian number (+995)."),
    )

    # Gift
    gift_wrap = forms.BooleanField(label=_("Gift wrap"), required=False)
    gift_note = forms.CharField(
        label=_("Gift note"),
        max_length=GIFT_NOTE_MAX,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("We write it by hand on a card."),
    )
    hide_prices_on_slip = forms.BooleanField(
        label=_("Hide prices on the packing slip"), required=False
    )

    # Payment and consents
    payment_method = forms.ChoiceField(
        label=_("Payment"), choices=Order.PaymentMethod.choices, widget=forms.RadioSelect
    )
    consent_terms = forms.BooleanField(
        label=_("I accept the terms and conditions"),
        error_messages={"required": _("Please accept the terms and conditions.")},
    )
    consent_privacy = forms.BooleanField(
        label=_("I have read the privacy policy"),
        error_messages={"required": _("Please confirm you have read the privacy policy.")},
    )
    consent_marketing = forms.BooleanField(
        label=_("Send me news about new pieces by email (optional)"), required=False
    )

    expected_total = forms.IntegerField(required=False, widget=forms.HiddenInput)
    checkout_token = forms.CharField(max_length=64, widget=forms.HiddenInput)

    def clean_phone(self) -> str:
        return normalize_phone(self.cleaned_data["phone"])

    def clean_recipient_phone(self) -> str:
        raw = self.cleaned_data["recipient_phone"].strip()
        return normalize_phone(raw, georgian_only=True) if raw else ""

    def clean(self):
        data = super().clean()
        option: DeliveryOption | None = data.get("delivery")
        if option and option.requires_address:
            if not option.fixed_city and not data.get("city", "").strip():
                self.add_error("city", ValidationError(_("Enter the city or village.")))
            if not data.get("address_line", "").strip():
                self.add_error("address_line", ValidationError(_("Enter the delivery address.")))
        return data

    def to_checkout_data(self) -> CheckoutData:
        d = self.cleaned_data
        option = d["delivery"]
        return CheckoutData(
            first_name=d["first_name"].strip(),
            last_name=d["last_name"].strip(),
            email=d["email"],
            phone=d["phone"],
            delivery_option=option,
            payment_method=d["payment_method"],
            city=d["city"].strip() if option.requires_address else "",
            address_line=d["address_line"].strip() if option.requires_address else "",
            delivery_notes=d["delivery_notes"].strip(),
            recipient_name=d["recipient_name"].strip(),
            recipient_phone=d["recipient_phone"],
            gift_wrap=d["gift_wrap"],
            gift_note=d["gift_note"].strip(),
            hide_prices_on_slip=d["hide_prices_on_slip"],
            consent_terms=d["consent_terms"],
            consent_privacy=d["consent_privacy"],
            consent_marketing=d["consent_marketing"],
            expected_total=d.get("expected_total"),
            checkout_token=d["checkout_token"],
        )
