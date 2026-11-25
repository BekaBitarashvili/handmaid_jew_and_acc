"""Demo hero slides and intro line (dev only). Copy is placeholder text the owner replaces."""

from apps.core.models import SiteSettings
from apps.core.placeholders import hero_image

from .models import HeroSlide

SLIDES = [
    # title en, title ka, subtitle en, subtitle ka
    (
        "Made by hand, made to last",
        "ხელით შექმნილი, დიდხანს სატარებელი",
        "Natural stones, slow work, one piece at a time.",
        "ბუნებრივი ქვები, აუჩქარებელი შრომა, თითო ნივთი ერთხელ.",
    ),
    (
        "Quiet colours of natural stone",
        "ბუნებრივი ქვის მშვიდი ფერები",
        "Amber, lapis and pearl, set in silver and brass.",
        "ქარვა, ლაჟვარდი და მარგალიტი — ვერცხლსა და თითბერში.",
    ),
    (
        "Pieces made only once",
        "ნივთები, რომლებიც მხოლოდ ერთხელ იქმნება",
        "When it is gone, a similar one can be made for you.",
        "როცა ნივთი გაიყიდება, შეგვიძლია მსგავსი შევქმნათ.",
    ),
]


def seed_hero() -> str:
    if HeroSlide.objects.exists():
        return "kept"
    for order, (title_en, title_ka, sub_en, sub_ka) in enumerate(SLIDES):
        HeroSlide.objects.create(
            image=hero_image(order, f"demo-hero-{order + 1}.jpg"),
            title_en=title_en,
            title_ka=title_ka,
            subtitle_en=sub_en,
            subtitle_ka=sub_ka,
            primary_text_en="Shop Now",
            primary_text_ka="ყიდვა",
            primary_link="/shop/",
            secondary_text_en="Explore Collections",
            secondary_text_ka="კოლექციების ნახვა",
            secondary_link="/shop/new/",
            sort_order=order,
        )
    site = SiteSettings.load()
    if not site.intro_text_en:
        site.intro_text_en = (
            "A small atelier of handmade jewelry and accessories — natural stones, "
            "one piece at a time."
        )
        site.intro_text_ka = (
            "ხელნაკეთი სამკაულებისა და აქსესუარების პატარა ატელიე — ბუნებრივი ქვები, "
            "თითო ნივთი ერთხელ."
        )
        site.save()
    return f"{len(SLIDES)} created (+ demo intro line)"
