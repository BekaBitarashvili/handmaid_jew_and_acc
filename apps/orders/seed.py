"""Demo delivery options and demo orders (dev only).

Delivery prices and times are the owner's decision (SPEC §14.2): these are clearly demo
values so the cart's "Delivery from X" can be judged. Demo orders go through the real
services (place → pay → status changes), so the admin and Mailpit show every state.
"""

from datetime import timedelta

from django.utils import timezone

from .models import DeliveryOption, Order

OPTIONS = [
    # code, ka, en, needs an address, demo price (tetri)
    ("courier_tbilisi", "კურიერი თბილისში", "Courier in Tbilisi", True, 600),
    ("courier_regions", "კურიერი რეგიონებში", "Courier to the regions", True, 1000),
    ("pickup", "თვითგატანა", "Pickup", False, 0),
]


def seed_delivery_options() -> str:
    created = priced = 0
    for order, (code, ka, en, needs_address, demo_price) in enumerate(OPTIONS):
        option, was_created = DeliveryOption.objects.get_or_create(
            code=code,
            defaults={
                "name_ka": ka,
                "name_en": en,
                "price": demo_price,
                "estimated_days_ka": "დასაზუსტებელია",
                "estimated_days_en": "TBD",
                "requires_address": needs_address,
                "sort_order": order,
            },
        )
        created += was_created
        if not was_created and option.price == 0 and demo_price:  # older seeds used 0 ₾
            option.price = demo_price
            option.save(update_fields=["price"])
            priced += 1
    return f"{created} created, {priced} given demo prices (the owner sets the real ones)"


class _Session(dict):
    modified = False


# product (en name), variant (en name or None), qty, language, customer, extras, story
DEMO_ORDERS = [
    (
        "Beaded bracelet",
        "M",
        2,
        "ka",
        ("ნინო", "ბერიძე", "+995555123456"),
        {
            "recipient_name": "თამარ ბერიძე",
            "recipient_phone": "+995599112233",
            "gift_wrap": True,
            "gift_note": "გილოცავ დაბადების დღეს! ❤",
            "hide_prices_on_slip": True,
        },
        ["paid"],
    ),
    (
        "Knitted headscarf",
        "Terracotta",
        1,
        "en",
        ("Anna", "Smith", "+447700900123"),
        {},
        ["paid", "processing"],
    ),
    (
        "Vintage silver bracelet",
        None,
        1,
        "ka",
        ("გიორგი", "კაპანაძე", "+995577445566"),
        {},
        ["paid", "processing", "shipped"],
    ),
    (
        "Agate necklace",
        None,
        1,
        "en",
        ("Mariam", "Lomidze", "+995591223344"),
        {},
        ["paid", "processing", "shipped", "delivered"],
    ),
    (
        "Pearl necklace",
        None,
        1,
        "ka",
        ("ეკა", "ჯაფარიძე", "+995555987654"),
        {},
        ["paid", "cancelled"],
    ),
    ("Turquoise cuff", None, 1, "en", ("Luka", "Meskhi", "+995568112233"), {}, ["late"]),
    (
        "Turquoise bead necklace",
        None,
        1,
        "ka",
        ("სალომე", "ნოზაძე", "+995599001122"),
        {},
        ["waiting"],
    ),
]


def seed_orders() -> str:
    """Demo orders in every state (only when there are none)."""
    if Order.objects.exists():
        return "kept"
    from apps.cart.services import SessionCart
    from apps.catalog.models import ProductVariant
    from apps.payments.models import Payment

    from .services import CheckoutData, change_status, confirm_payment, fail_payment, place_order

    tbilisi = DeliveryOption.objects.filter(code="courier_tbilisi").first()
    regions = DeliveryOption.objects.filter(code="courier_regions").first()
    if not (tbilisi and regions):
        return "skipped (no delivery options)"
    made = 0
    now = timezone.now()
    for index, (product, variant_name, qty, language, who, extras, story) in enumerate(DEMO_ORDERS):
        variants = ProductVariant.objects.filter(product__name_en=product)
        if variant_name:
            variants = variants.filter(name_en=variant_name)
        variant = variants.first()
        if variant is None or variant.available < qty:
            continue
        option = tbilisi if index % 2 == 0 else regions

        def place(
            variant=variant,
            qty=qty,
            language=language,
            who=who,
            extras=extras,
            index=index,
            option=option,
        ):
            cart = SessionCart(_Session())
            cart.add(variant, qty=qty)
            cart.build()
            first, last, phone = who
            data = CheckoutData(
                first_name=first,
                last_name=last,
                email=f"demo{index + 1}@example.com",
                phone=phone,
                delivery_option=option,
                payment_method="bog" if index % 2 == 0 else "tbc",
                city="ქუთაისი" if option == regions else "",
                address_line="რუსთაველის გამზ. 12" if language == "ka" else "12 Rustaveli Ave",
                consent_terms=True,
                consent_privacy=True,
                **extras,
            )
            return place_order(cart, data, language=language, ip_address="127.0.0.1")

        order = place()
        if "late" in story:  # paid after its hold ended, but someone else bought the piece
            fail_payment(order.pk, expired=True)
            buyer = place(who=("ქეთი", "გელაშვილი", "+995551778899"), language="ka")
            Payment.objects.create(
                order=buyer,
                provider="fake",
                provider_order_id=f"fake-demo-{index}b",
                amount=buyer.total,
                status=Payment.Status.PAID,
            )
            confirm_payment(buyer.pk)
        if "waiting" not in story:
            Payment.objects.create(
                order=order,
                provider="fake",
                provider_order_id=f"fake-demo-{index}",
                amount=order.total,
                status=Payment.Status.PAID,
            )
            order = confirm_payment(order.pk)
        for step in story:
            if step in ("processing", "shipped", "delivered", "cancelled"):
                note = {
                    "shipped": "ხვალ, 12:00–15:00" if language == "ka" else "Tomorrow, 12:00–15:00",
                    "cancelled": "Demo: cancelled by the shop.",
                }.get(step)
                order = change_status(
                    order, step, customer_note=note if step in ("shipped", "cancelled") else None
                )
        # Spread the demo over the last days (newest last).
        when = now - timedelta(days=len(DEMO_ORDERS) - index, hours=index)
        Order.objects.filter(pk=order.pk).update(created_at=when)
        made += 1
    return f"{made} demo orders (emails sent to the dev mailbox)"
