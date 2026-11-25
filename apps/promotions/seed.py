"""Demo sale (dev only) so the Sale page and the home banner have content."""

from apps.catalog.models import Category
from apps.core.placeholders import banner_image

from .models import Sale


def seed_sale() -> str:
    if Sale.objects.exists():
        return "kept"
    sale = Sale.objects.create(
        name="Demo sale (dev)",
        discount_type=Sale.DiscountType.PERCENT,
        percent=30,
        show_on_home=True,
        banner_title_en="Special Offers",
        banner_title_ka="სპეციალური შეთავაზება",
        banner_subtitle_en="Selected pieces at 30% off",
        banner_subtitle_ka="შერჩეული ნივთები 30%-იანი ფასდაკლებით",
        banner_image=banner_image("demo-banner.jpg"),
    )
    sale.categories.set(Category.objects.filter(code__in=["EAR", "SCA"]))
    return "1 created (30% on earrings + headscarves, home banner on)"
