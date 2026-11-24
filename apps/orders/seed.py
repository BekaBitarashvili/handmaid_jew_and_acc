"""Demo delivery options. Prices and delivery times are the owner's decision
(SPEC §14.2), so they are seeded as 0 ₾ / "TBD" placeholders."""

from .models import DeliveryOption

OPTIONS = [
    ("courier_tbilisi", "კურიერი თბილისში", "Courier in Tbilisi", True),
    ("courier_regions", "კურიერი რეგიონებში", "Courier to the regions", True),
    ("pickup", "თვითგატანა", "Pickup", False),
]


def seed_delivery_options() -> str:
    created = 0
    for order, (code, ka, en, needs_address) in enumerate(OPTIONS):
        _, was_created = DeliveryOption.objects.get_or_create(
            code=code,
            defaults={
                "name_ka": ka,
                "name_en": en,
                "price": 0,
                "estimated_days_ka": "დასაზუსტებელია",
                "estimated_days_en": "TBD",
                "requires_address": needs_address,
                "sort_order": order,
            },
        )
        created += was_created
    return f"{created} created (prices 0 ₾ until the owner sets them)"
