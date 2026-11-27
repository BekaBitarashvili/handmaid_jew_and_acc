"""Demo delivery options (dev only). Prices and delivery times are the owner's decision
(SPEC §14.2): these are clearly demo values so the cart's "Delivery from X" can be judged."""

from .models import DeliveryOption

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
