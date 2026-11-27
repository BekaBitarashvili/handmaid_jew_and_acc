from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.widgets import UnfoldAdminTextareaWidget, UnfoldBooleanWidget

from .models import Order


class StatusChangeForm(forms.Form):
    """Confirmation step for a status change. The fields depend on where the order goes."""

    note = forms.CharField(
        label=_("Internal note"),
        required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}),
        help_text=_("Only you see this (status history)."),
    )
    customer_note = forms.CharField(
        label=_("Note for the customer"),
        required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}),
        help_text=_("Shown on the order page and in the email, e.g. a delivery time window."),
    )
    return_to_shop = forms.BooleanField(
        label=_("Return the pieces to the shop"),
        required=False,
        initial=True,
        widget=UnfoldBooleanWidget,
        help_text=_("One-of-a-kind pieces go back on sale."),
    )

    def __init__(self, *args, order: Order, to: str, **kwargs):
        super().__init__(*args, **kwargs)
        paid = order.payment_status == Order.PaymentStatus.PAID
        if to not in (Order.Status.SHIPPED, Order.Status.CANCELLED) or (
            to == Order.Status.CANCELLED and not paid
        ):
            del self.fields["customer_note"]
        elif order.customer_note:
            self.fields["customer_note"].initial = order.customer_note
        if not (to == Order.Status.CANCELLED and paid):
            del self.fields["return_to_shop"]


class NoteForm(forms.Form):
    note = forms.CharField(
        label=_("Note"), widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}), required=False
    )
