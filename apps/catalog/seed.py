"""Demo catalog for local development (`manage.py seed_demo`). Idempotent.

Texts are neutral placeholders: stone descriptions mention only origin and color,
never healing or "energy" claims. Prices are demo values.
"""

import io
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from .models import Category, Material, Product, ProductImage, ProductVariant, Stone
from .services.products import ensure_default_variant, prepare_product_for_save
from .services.slugs import fill_translated_slugs

CATEGORIES = [
    # code, ka, en, parent code
    ("NEC", "ყელსაბამები", "Necklaces", None),
    ("EAR", "საყურეები", "Earrings", None),
    ("BRA", "სამაჯურები", "Bracelets", None),
    ("VIN", "ვინტაჟი", "Vintage", None),
    ("SCA", "ნაქსოვი თავსაფრები", "Knitted headscarves", None),
    ("BRO", "ბროშები", "Brooches", "VIN"),
]

STONES = [
    # en, ka, color, short en, short ka
    (
        "Amber",
        "ქარვა",
        "#C8862A",
        "Fossilised tree resin in warm honey tones.",
        "გაქვავებული ფისი თაფლისფერ ტონებში.",
    ),
    (
        "Lapis lazuli",
        "ლაჟვარდი",
        "#26619C",
        "Deep blue stone with golden flecks.",
        "მუქი ლურჯი ქვა ოქროსფერი წინწკლებით.",
    ),
    (
        "Carnelian",
        "სარდიონი",
        "#B3412A",
        "Translucent orange-red chalcedony.",
        "გამჭვირვალე ნარინჯისფერ-წითელი ქალცედონი.",
    ),
    (
        "Rock crystal",
        "მთის ბროლი",
        "#D9D6CF",
        "Clear quartz, cool and luminous.",
        "გამჭვირვალე კვარცი, ცივი და მანათობელი.",
    ),
    (
        "Turquoise",
        "ფირუზი",
        "#3FA9A0",
        "Sky-blue to green opaque stone.",
        "ცისფერიდან მწვანემდე გაუმჭვირვალე ქვა.",
    ),
    ("Garnet", "გრანატი", "#7B1E2B", "Dark wine-red crystal.", "მუქი ღვინისფერი კრისტალი."),
    (
        "Agate",
        "აქატი",
        "#8E7D6B",
        "Banded chalcedony in earthy layers.",
        "ზოლიანი ქალცედონი მიწისფერ ფენებად.",
    ),
    ("Rose quartz", "ვარდისფერი კვარცი", "#E2B4AF", "Soft pink quartz.", "ნაზი ვარდისფერი კვარცი."),
]

MATERIALS = [
    ("Silver 925", "ვერცხლი 925"),
    ("Brass", "თითბერი"),
    ("Glass beads", "მინის მძივები"),
    ("Wool", "მატყლი"),
    ("Leather cord", "ტყავის ზონარი"),
    ("Freshwater pearl", "მტკნარი წყლის მარგალიტი"),
]

S = Product.Status
PRODUCTS = [
    # category, en, ka, stones, materials, price GEL, status, variants [(en, ka, stock)] or None
    ("NEC", "Amber necklace", "ქარვის ყელსაბამი", ["Amber"], ["Silver 925"], 145, S.ACTIVE, None),
    (
        "NEC",
        "Lapis lazuli necklace",
        "ლაჟვარდის ყელსაბამი",
        ["Lapis lazuli"],
        ["Silver 925"],
        180,
        S.ACTIVE,
        None,
    ),
    (
        "NEC",
        "Turquoise bead necklace",
        "ფირუზის მძივების ყელსაბამი",
        ["Turquoise"],
        ["Glass beads"],
        95,
        S.ACTIVE,
        None,
    ),
    (
        "NEC",
        "Rock crystal pendant",
        "მთის ბროლის გულსაკიდი",
        ["Rock crystal"],
        ["Silver 925"],
        120,
        S.SOLD,
        None,
    ),
    (
        "NEC",
        "Pearl necklace",
        "მარგალიტის ყელსაბამი",
        [],
        ["Freshwater pearl", "Silver 925"],
        210,
        S.ACTIVE,
        None,
    ),
    ("NEC", "Agate necklace", "აქატის ყელსაბამი", ["Agate"], ["Silver 925"], 125, S.ACTIVE, None),
    (
        "NEC",
        "Garnet necklace",
        "გრანატის ყელსაბამი",
        ["Garnet"],
        ["Silver 925"],
        155,
        S.HIDDEN,
        None,
    ),
    (
        "EAR",
        "Carnelian earrings",
        "სარდიონის საყურეები",
        ["Carnelian"],
        ["Silver 925"],
        85,
        S.ACTIVE,
        None,
    ),
    (
        "EAR",
        "Amber drop earrings",
        "ქარვის წვეთის საყურეები",
        ["Amber"],
        ["Brass"],
        70,
        S.ACTIVE,
        None,
    ),
    ("EAR", "Garnet studs", "გრანატის საყურეები", ["Garnet"], ["Silver 925"], 90, S.SOLD, None),
    (
        "EAR",
        "Rose quartz earrings",
        "ვარდისფერი კვარცის საყურეები",
        ["Rose quartz"],
        ["Silver 925"],
        75,
        S.DRAFT,
        None,
    ),
    ("BRA", "Agate bracelet", "აქატის სამაჯური", ["Agate"], ["Leather cord"], 60, S.ACTIVE, None),
    (
        "BRA",
        "Lapis lazuli bracelet",
        "ლაჟვარდის სამაჯური",
        ["Lapis lazuli"],
        ["Silver 925"],
        110,
        S.ACTIVE,
        None,
    ),
    (
        "BRA",
        "Beaded bracelet",
        "მძივების სამაჯური",
        ["Turquoise"],
        ["Glass beads"],
        45,
        S.ACTIVE,
        [("S", "S", 3), ("M", "M", 5), ("L", "L", 2)],
    ),
    ("BRA", "Turquoise cuff", "ფირუზის სამაჯური", ["Turquoise"], ["Brass"], 130, S.ACTIVE, None),
    (
        "BRO",
        "Vintage amber brooch",
        "ვინტაჟური ქარვის ბროში",
        ["Amber"],
        ["Brass"],
        160,
        S.ACTIVE,
        None,
    ),
    (
        "VIN",
        "Vintage pearl earrings",
        "ვინტაჟური მარგალიტის საყურეები",
        [],
        ["Freshwater pearl"],
        140,
        S.SOLD,
        None,
    ),
    (
        "VIN",
        "Vintage silver bracelet",
        "ვინტაჟური ვერცხლის სამაჯური",
        [],
        ["Silver 925"],
        190,
        S.ACTIVE,
        None,
    ),
    (
        "SCA",
        "Knitted headscarf",
        "ნაქსოვი თავსაფარი",
        [],
        ["Wool"],
        85,
        S.ACTIVE,
        [("Beige", "ბეჟი", 2), ("Terracotta", "ტერაკოტა", 1), ("Olive", "ზეთისხილისფერი", 3)],
    ),
    (
        "SCA",
        "Winter wool headscarf",
        "მატყლის თავსაფარი „ზამთარი“",
        [],
        ["Wool"],
        95,
        S.ACTIVE,
        None,
    ),
]

BACKDROPS = ((242, 235, 223), (227, 213, 193))  # cream, sand
SHORT_EN = {False: "Handmade, one of a kind.", True: "Handmade in small batches."}
SHORT_KA = {False: "ხელნაკეთი, ერთადერთი ეგზემპლარი.", True: "ხელნაკეთი, მცირე პარტიით."}


def placeholder_photo(color_hex: str, label: str, backdrop: tuple[int, int, int]) -> ContentFile:
    """4:5 placeholder: a faceted 'stone' in the stone's color on a calm backdrop."""
    width, height = 1600, 2000
    image = Image.new("RGB", (width, height), backdrop)
    draw = ImageDraw.Draw(image)
    rgb = tuple(int(color_hex[i : i + 2], 16) for i in (1, 3, 5))
    cx, cy, r = width // 2, height // 2 - 80, 360
    gem = [(cx, cy - r), (cx + r, cy - r // 3), (cx, cy + r), (cx - r, cy - r // 3)]
    draw.polygon(gem, fill=rgb, outline=(46, 33, 26), width=4)
    draw.line([(cx - r, cy - r // 3), (cx + r, cy - r // 3)], fill=(46, 33, 26), width=3)
    font = ImageFont.load_default(size=44)
    draw.text((cx, height - 220), label, fill=(122, 102, 80), font=font, anchor="mm")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return ContentFile(buffer.getvalue(), name=f"demo-{label.lower()}.jpg")


@transaction.atomic
def seed_catalog() -> str:
    created = {"categories": 0, "stones": 0, "materials": 0, "products": 0}

    categories: dict[str, Category] = {}
    for order, (code, ka, en, parent) in enumerate(CATEGORIES):
        category = Category.objects.filter(code=code).first()
        if category is None:
            category = Category(code=code, name_ka=ka, name_en=en, sort_order=order)
            category.parent = categories.get(parent)
            fill_translated_slugs(category)
            category.save()
            created["categories"] += 1
        categories[code] = category

    stones: dict[str, Stone] = {}
    for order, (en, ka, color, short_en, short_ka) in enumerate(STONES):
        stone = Stone.objects.filter(name_en=en).first()
        if stone is None:
            stone = Stone(
                name_en=en,
                name_ka=ka,
                color_hex=color,
                short_description_en=short_en,
                short_description_ka=short_ka,
                story_en=f"<p>{short_en} Demo text — the owner writes the real story.</p>",
                story_ka=f"<p>{short_ka} სადემონსტრაციო ტექსტი.</p>",
                sort_order=order,
            )
            fill_translated_slugs(stone)
            stone.save()
            created["stones"] += 1
        stones[en] = stone

    materials: dict[str, Material] = {}
    for order, (en, ka) in enumerate(MATERIALS):
        material, was_created = Material.objects.get_or_create(
            name_en=en, defaults={"name_ka": ka, "sort_order": order}
        )
        created["materials"] += was_created
        materials[en] = material

    now = timezone.now()
    for index, (code, en, ka, stone_names, material_names, gel, status, variants) in enumerate(
        PRODUCTS
    ):
        if Product.objects.filter(name_en=en).exists():
            continue
        product = Product(
            category=categories[code],
            name_en=en,
            name_ka=ka,
            short_description_en=SHORT_EN[bool(variants)],
            short_description_ka=SHORT_KA[bool(variants)],
            description_en="<p>Demo description. The owner replaces this text.</p>",
            description_ka="<p>სადემონსტრაციო აღწერა.</p>",
            care_instructions_en="Keep dry and away from perfume.",
            care_instructions_ka="შეინახეთ მშრალ ადგილას, სუნამოსგან მოშორებით.",
            dimensions_en="Length 45 cm" if code == "NEC" else "",
            dimensions_ka="სიგრძე 45 სმ" if code == "NEC" else "",
            price=gel * 100,
            status=status,
            is_unique=variants is None,
            is_featured=index in (0, 1, 15),
            hours_to_make=4 + index % 6,
        )
        prepare_product_for_save(product, is_new=True)
        if status in (S.ACTIVE, S.SOLD, S.HIDDEN):
            product.published_at = now - timedelta(days=index * 4)
        product.save()
        product.stones.set([stones[n] for n in stone_names])
        product.materials.set([materials[n] for n in material_names])

        if variants:
            for order, (v_en, v_ka, stock) in enumerate(variants):
                ProductVariant.objects.create(
                    product=product,
                    name_en=v_en,
                    name_ka=v_ka,
                    sku_suffix=v_en[:3].upper(),
                    stock=stock,
                    sort_order=order,
                    is_default=order == 0,
                )
        variant = ensure_default_variant(product)
        if status == S.SOLD:
            variant.stock = 0
            variant.save(update_fields=["stock"])

        color = stones[stone_names[0]].color_hex if stone_names else "#B08D57"
        for photo_index, backdrop in enumerate(BACKDROPS):
            ProductImage.objects.create(
                product=product,
                image=placeholder_photo(color, product.sku, backdrop),
                alt_ka=f"{ka} — ფოტო {photo_index + 1}",
                alt_en=f"{en} — photo {photo_index + 1}",
                sort_order=photo_index,
            )
        created["products"] += 1

    return ", ".join(f"{count} {name}" for name, count in created.items()) + " created"
