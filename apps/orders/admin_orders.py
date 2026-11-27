"""Orders in the admin (SPEC §10): a phone-friendly list that opens on what needs action,
a detail page with big status buttons, tap-to-call / tap-to-email, internal notes and a
printable packing slip. All changes go through orders.services."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display

from apps.core.admin_base import BaseModelAdmin, BaseTabularInline
from apps.core.money import format_gel
from apps.core.phones import format_phone
from apps.payments.models import Payment

from .admin_forms import NoteForm, StatusChangeForm
from .models import Order, OrderItem, OrderStatusHistory
from .services import (
    InvalidTransition,
    allowed_next,
    change_status,
    mark_refunded,
    resolve_attention,
)

S = Order.Status
STATUS_COLORS = {
    S.AWAITING_PAYMENT: "info",
    S.NEW: "warning",
    S.PROCESSING: "warning",
    S.SHIPPED: "info",
    S.DELIVERED: "success",
    S.CANCELLED: "danger",
}
PAYMENT_COLORS = {"pending": "info", "paid": "success", "failed": "danger", "refunded": "danger"}
# The owner's next step, worded as an action.
ACTION_LABELS = {
    S.PROCESSING: _("Start preparing"),
    S.SHIPPED: _("Mark as shipped"),
    S.DELIVERED: _("Mark as delivered"),
    S.CANCELLED: _("Cancel order"),
}
NEEDS_ACTION = (S.NEW, S.PROCESSING, S.SHIPPED)


class ViewFilter(admin.SimpleListFilter):
    """Opens on "Needs action": new, being prepared, shipped, or flagged."""

    title = _("show")
    parameter_name = "view"

    def lookups(self, request, model_admin):
        return (("all", _("All orders")),)

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": _("Needs action"),
        }
        yield from (
            {
                "selected": self.value() == value,
                "query_string": changelist.get_query_string({self.parameter_name: value}),
                "display": label,
            }
            for value, label in self.lookup_choices
        )

    def queryset(self, request, queryset):
        if self.value() == "all":
            return queryset
        return queryset.filter(Q(status__in=NEEDS_ACTION) | Q(needs_attention=True))


class ReadOnlyInline(BaseTabularInline):
    extra = 0
    max_num = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OrderItemInline(ReadOnlyInline):
    model = OrderItem
    fields = ("photo", "product_name", "variant_name", "sku", "qty", "price", "line")
    readonly_fields = fields
    verbose_name_plural = _("pieces")

    @display(description="")
    def photo(self, obj: OrderItem):
        if not obj.image_url:
            return ""
        return format_html(
            '<img src="{}" alt="" width="56" height="56" style="object-fit:cover">', obj.image_url
        )

    @display(description=_("price"))
    def price(self, obj: OrderItem):
        if obj.on_sale:
            return format_html(
                "<s>{}</s> {}", format_gel(obj.original_unit_price), format_gel(obj.unit_price)
            )
        return format_gel(obj.unit_price)

    @display(description=_("total"))
    def line(self, obj: OrderItem):
        return format_gel(obj.line_total)


class HistoryInline(ReadOnlyInline):
    model = OrderStatusHistory
    fields = ("created_at", "status_change", "note", "changed_by")
    readonly_fields = fields

    @display(description=_("status"))
    def status_change(self, obj: OrderStatusHistory):
        return obj.to_label


class PaymentInline(ReadOnlyInline):
    model = Payment
    fields = ("created_at", "provider", "provider_order_id", "amount_display", "status")
    readonly_fields = fields

    @display(description=_("amount"))
    def amount_display(self, obj: Payment):
        return format_gel(obj.amount)


@admin.register(Order)
class OrderAdmin(BaseModelAdmin):
    list_display = ("order", "customer", "total_display", "status_badge", "payment_badge")
    list_filter = (ViewFilter, "status", "payment_status", "needs_attention", "created_at")
    search_fields = (
        "number",
        "first_name",
        "last_name",
        "email",
        "phone",
        "recipient_name",
        "recipient_phone",
    )
    date_hierarchy = "created_at"
    inlines = (OrderItemInline, HistoryInline, PaymentInline)
    change_form_template = "admin/orders/order/change_form.html"
    warn_unsaved_form = False
    fieldsets = (
        (
            _("Customer"),
            {"fields": ("customer_name_display", "phone_link", "email_link", "language")},
        ),
        (
            _("Delivery"),
            {
                "fields": (
                    "delivery_name",
                    "address_display",
                    "delivery_notes",
                    "recipient_display",
                )
            },
        ),
        (_("Gift"), {"fields": ("gift_wrap", "gift_note", "hide_prices_on_slip")}),
        (
            _("Totals"),
            {
                "fields": (
                    "subtotal_display",
                    "gift_wrap_display",
                    "shipping_display",
                    "total_display",
                )
            },
        ),
        (
            _("Payment and consents"),
            {
                "fields": (
                    "payment_method",
                    "payment_status",
                    "paid_at",
                    "consents_display",
                    "created_at",
                )
            },
        ),
        (_("Notes"), {"fields": ("customer_note", "internal_notes")}),
    )
    readonly_fields = (
        "customer_name_display",
        "phone_link",
        "email_link",
        "language",
        "delivery_name",
        "address_display",
        "delivery_notes",
        "recipient_display",
        "gift_wrap",
        "gift_note",
        "hide_prices_on_slip",
        "subtotal_display",
        "gift_wrap_display",
        "shipping_display",
        "total_display",
        "payment_method",
        "payment_status",
        "paid_at",
        "consents_display",
        "created_at",
    )

    def has_add_permission(self, request):
        return False  # orders come from the checkout

    def has_delete_permission(self, request, obj=None):
        return False  # kept for the books; cancel instead

    # --- list ------------------------------------------------------------------------

    @display(description=_("order"), ordering="created_at")
    def order(self, obj: Order):
        flag = format_html(' <span title="{}">⚠</span>', _("needs attention"))
        return format_html(
            "<strong>{}</strong>{}<br><small>{}</small>",
            obj.number,
            flag if obj.needs_attention else "",
            obj.created_at.strftime("%d.%m %H:%M"),
        )

    @display(description=_("customer"))
    def customer(self, obj: Order):
        return format_html("{}<br><small>{}</small>", obj.customer_name, format_phone(obj.phone))

    @display(description=_("total"), ordering="total")
    def total_display(self, obj: Order):
        return format_gel(obj.total)

    @display(description=_("status"), ordering="status", label=STATUS_COLORS)
    def status_badge(self, obj: Order):
        return obj.status, obj.get_status_display()

    @display(description=_("payment"), ordering="payment_status", label=PAYMENT_COLORS)
    def payment_badge(self, obj: Order):
        return obj.payment_status, obj.get_payment_status_display()

    # --- detail ----------------------------------------------------------------------

    @display(description=_("name"))
    def customer_name_display(self, obj: Order):
        return obj.customer_name

    @display(description=_("phone"))
    def phone_link(self, obj: Order):
        return format_html('<a href="tel:{}">{}</a>', obj.phone, format_phone(obj.phone))

    @display(description=_("email"))
    def email_link(self, obj: Order):
        return format_html('<a href="mailto:{0}">{0}</a>', obj.email)

    @display(description=_("address"))
    def address_display(self, obj: Order):
        if not obj.requires_address:
            return "—"
        return ", ".join(part for part in (obj.address_line, obj.city) if part)

    @display(description=_("recipient"))
    def recipient_display(self, obj: Order):
        if not obj.has_recipient:
            return "—"
        phone = (
            format_html(
                ' · <a href="tel:{}">{}</a>', obj.recipient_phone, format_phone(obj.recipient_phone)
            )
            if obj.recipient_phone
            else ""
        )
        return format_html("<strong>{}</strong>{}", obj.recipient_name, phone)

    @display(description=_("pieces"))
    def subtotal_display(self, obj: Order):
        return format_gel(obj.subtotal)

    @display(description=_("gift wrap"))
    def gift_wrap_display(self, obj: Order):
        return format_gel(obj.gift_wrap_price) if obj.gift_wrap else "—"

    @display(description=_("delivery"))
    def shipping_display(self, obj: Order):
        return format_gel(obj.shipping_price)

    @display(description=_("consents"))
    def consents_display(self, obj: Order):
        given = [
            label
            for flag, label in (
                (obj.consent_terms, _("terms")),
                (obj.consent_privacy, _("privacy")),
                (obj.consent_marketing, _("news by email")),
            )
            if flag
        ]
        when = obj.consented_at.strftime("%d.%m.%Y %H:%M") if obj.consented_at else ""
        return f"{', '.join(str(g) for g in given)} — {when}" if given else "—"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        order = self.get_object(request, object_id)
        extra = extra_context or {}
        if order is not None:
            extra.update(
                {
                    "order_actions": [
                        (to, ACTION_LABELS[to], to == S.CANCELLED) for to in allowed_next(order)
                    ],
                    "can_refund": order.status == S.CANCELLED
                    and order.payment_status == Order.PaymentStatus.PAID,
                    "order_phone": format_phone(order.phone),
                    "recipient_phone": format_phone(order.recipient_phone),
                }
            )
        return super().change_view(request, object_id, form_url, extra_context=extra)

    # --- custom views ------------------------------------------------------------------

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path(
                "<int:object_id>/status/<str:to>/",
                view(self.status_view),
                name="orders_order_status",
            ),
            path("<int:object_id>/refund/", view(self.refund_view), name="orders_order_refund"),
            path("<int:object_id>/resolve/", view(self.resolve_view), name="orders_order_resolve"),
            path("<int:object_id>/slip/", view(self.slip_view), name="orders_order_slip"),
            *super().get_urls(),
        ]

    def _order(self, request, object_id) -> Order:
        order = get_object_or_404(Order, pk=object_id)
        if not self.has_change_permission(request, order):
            raise PermissionDenied
        return order

    def _back(self, order: Order):
        return redirect(reverse("admin:orders_order_change", args=[order.pk]))

    def _confirm(self, request, order, form, title, submit, danger=False):
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": order,
            "title": title,
            "form": form,
            "submit_label": submit,
            "danger": danger,
            "back_url": reverse("admin:orders_order_change", args=[order.pk]),
        }
        return render(request, "admin/orders/order/confirm.html", context)

    def status_view(self, request, object_id, to):
        order = self._order(request, object_id)
        if to not in allowed_next(order):
            messages.error(request, _("This status change is not possible."))
            return self._back(order)
        form = StatusChangeForm(
            request.POST if request.method == "POST" else None, order=order, to=to
        )
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                change_status(
                    order,
                    to,
                    by=request.user,
                    note=data.get("note", ""),
                    customer_note=data.get("customer_note"),
                    return_to_shop=data.get("return_to_shop", True),
                )
            except InvalidTransition:
                messages.error(request, _("This status change is not possible."))
            else:
                messages.success(
                    request,
                    _("Order %(number)s: %(status)s.")
                    % {"number": order.number, "status": S(to).label},
                )
            return self._back(order)
        title = _("%(action)s — order %(number)s") % {
            "action": ACTION_LABELS[to],
            "number": order.number,
        }
        return self._confirm(request, order, form, title, ACTION_LABELS[to], to == S.CANCELLED)

    def refund_view(self, request, object_id):
        order = self._order(request, object_id)
        form = NoteForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                mark_refunded(order, by=request.user, note=form.cleaned_data["note"])
                messages.success(request, _("Marked as refunded."))
            except InvalidTransition:
                messages.error(request, _("Only a paid, cancelled order can be refunded."))
            return self._back(order)
        title = _("Mark order %(number)s as refunded") % {"number": order.number}
        return self._confirm(request, order, form, title, _("Mark refunded"))

    def resolve_view(self, request, object_id):
        order = self._order(request, object_id)
        form = NoteForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            resolve_attention(order, by=request.user, note=form.cleaned_data["note"])
            messages.success(request, _("Marked as resolved."))
            return self._back(order)
        title = _("Resolve order %(number)s") % {"number": order.number}
        return self._confirm(request, order, form, title, _("Resolved"))

    def slip_view(self, request, object_id):
        order = self._order(request, object_id)
        return render(
            request,
            "admin/orders/order/slip.html",
            {"order": order, "items": order.items.all()},
        )
