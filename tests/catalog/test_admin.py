from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders.models import DeliveryOption

from .factories import CategoryFactory, ProductFactory, ProductImageFactory, make_jpeg

pytestmark = pytest.mark.django_db
YEAR = timezone.localdate().year
KA_MO = Path(settings.BASE_DIR) / "locale" / "ka" / "LC_MESSAGES" / "django.mo"


@pytest.fixture
def admin_en(admin_client):
    admin_client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    return admin_client


def management(prefix: str, total: int = 0, initial: int = 0) -> dict:
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


def product_post(category, **overrides) -> dict:
    data = {
        "name_ka": "ქარვის ყელსაბამი",
        "name_en": "Amber necklace",
        "category": str(category.pk),
        "status": Product.Status.DRAFT,
        "price": "145.50",
        "is_unique": "on",
        "new_badge": Product.NewBadge.AUTO,
        "allow_commission_request": "on",
        **management("images"),
        **management("variants"),
    }
    data.update(overrides)
    return data


def existing_variant_forms(product) -> dict:
    data = management("variants", total=product.variants.count(), initial=product.variants.count())
    for i, v in enumerate(product.variants.all()):
        data.update(
            {
                f"variants-{i}-id": str(v.pk),
                f"variants-{i}-product": str(product.pk),
                f"variants-{i}-name_ka": v.name_ka or "",
                f"variants-{i}-name_en": v.name_en or "",
                f"variants-{i}-stock": str(v.stock),
                f"variants-{i}-sku_suffix": v.sku_suffix,
                f"variants-{i}-price_override": "",
                f"variants-{i}-is_default": "on" if v.is_default else "",
                f"variants-{i}-sort_order": str(v.sort_order),
            }
        )
    return data


class TestPagesRender:
    @pytest.mark.parametrize(
        "name",
        [
            "catalog_product",
            "catalog_category",
            "catalog_stone",
            "catalog_material",
            "orders_deliveryoption",
            "auth_user",
            "auth_group",
        ],
    )
    def test_changelist_and_add(self, admin_client, name):
        assert admin_client.get(reverse(f"admin:{name}_changelist")).status_code == 200
        assert admin_client.get(reverse(f"admin:{name}_add")).status_code == 200

    def test_product_change_page_with_photos(self, admin_client):
        product = ProductFactory()
        ProductImageFactory(product=product)
        response = admin_client.get(reverse("admin:catalog_product_change", args=[product.pk]))
        assert response.status_code == 200
        html = response.content.decode()
        assert 'name="name_ka"' in html and 'name="name_en"' in html  # ka/en tabs
        assert 'accept="image/*"' in html  # phone camera upload
        assert 'value="145"' in html  # price shown in lari, stored as 14500 tetri


class TestCreateProduct:
    def test_with_photos(self, admin_en):
        category = CategoryFactory(code="NEC")
        data = product_post(category)
        data["new_photos"] = [make_jpeg(name="a.jpg"), make_jpeg(name="b.jpg")]
        response = admin_en.post(reverse("admin:catalog_product_add"), data)
        assert response.status_code == 302, response.content.decode()[:3000]

        product = Product.objects.get()
        assert product.sku == f"NEC-{YEAR}-0001"
        assert product.price == 14550
        assert product.slug_ka == "karvis-qelsabami"
        images = list(product.images.all())
        assert [i.alt_ka for i in images] == ["ქარვის ყელსაბამი"] * 2
        assert all(i.image.name.endswith(".jpg") for i in images)
        (variant,) = product.variants.all()
        assert (variant.is_default, variant.stock) == (True, 1)

    def test_active_without_photos_is_refused(self, admin_en):
        data = product_post(CategoryFactory(), status=Product.Status.ACTIVE)
        response = admin_en.post(reverse("admin:catalog_product_add"), data)
        assert response.status_code == 200
        html = response.content.decode()
        assert "be Active yet" in html
        assert "Add at least one photo" in html
        assert not Product.objects.exists()

    def test_active_with_photos_publishes(self, admin_en):
        data = product_post(CategoryFactory(), status=Product.Status.ACTIVE)
        data["new_photos"] = [make_jpeg()]
        assert admin_en.post(reverse("admin:catalog_product_add"), data).status_code == 302
        assert Product.objects.get().published_at is not None

    def test_unique_piece_cannot_have_stock_above_one(self, admin_en):
        data = product_post(CategoryFactory())
        data.update(management("variants", total=1))
        data.update({"variants-0-stock": "2", "variants-0-is_default": "on"})
        response = admin_en.post(reverse("admin:catalog_product_add"), data)
        assert response.status_code == 200
        assert "can&#x27;t have more than 1 in stock" in response.content.decode()


class TestSkuNeverChanges:
    def test_changing_category_in_admin_keeps_sku(self, admin_en):
        product = ProductFactory(category=CategoryFactory(code="NEC"))
        original = product.sku
        other = CategoryFactory(code="VIN")
        data = product_post(other, sku="VIN-9999-9999")  # sku is read-only: ignored
        data.update(existing_variant_forms(product))
        url = reverse("admin:catalog_product_change", args=[product.pk])
        response = admin_en.post(url, data)
        assert response.status_code == 302, response.content.decode()[:3000]
        product.refresh_from_db()
        assert product.category == other
        assert product.sku == original

    def test_sku_is_not_an_input_on_change(self, admin_client):
        product = ProductFactory()
        html = admin_client.get(
            reverse("admin:catalog_product_change", args=[product.pk])
        ).content.decode()
        assert 'name="sku"' not in html
        assert product.sku in html


class TestActions:
    def run(self, client, action, products):
        return client.post(
            reverse("admin:catalog_product_changelist"),
            {"action": action, "_selected_action": [p.pk for p in products]},
            follow=True,
        )

    def test_show_requires_publish_rules(self, admin_en):
        bare = ProductFactory()
        ready = ProductFactory()
        ProductImageFactory(product=ready)
        response = self.run(admin_en, "make_visible", [bare, ready])
        bare.refresh_from_db()
        ready.refresh_from_db()
        assert bare.status == Product.Status.DRAFT
        assert ready.status == Product.Status.ACTIVE
        texts = " ".join(str(m) for m in get_messages(response.wsgi_request))
        assert "Add at least one photo" in texts

    def test_hide_and_mark_sold(self, admin_en):
        a, b = ProductFactory(status=Product.Status.ACTIVE), ProductFactory()
        self.run(admin_en, "make_hidden", [a])
        self.run(admin_en, "mark_as_sold", [b])
        a.refresh_from_db()
        b.refresh_from_db()
        assert a.status == Product.Status.HIDDEN
        assert (b.status, b.total_stock) == (Product.Status.SOLD, 0)

    def test_duplicate(self, admin_en):
        product = ProductFactory()
        self.run(admin_en, "duplicate", [product])
        assert Product.objects.count() == 2
        assert Product.objects.exclude(pk=product.pk).get().status == Product.Status.DRAFT


class TestAdminLanguage:
    def test_defaults_to_georgian(self, admin_client):
        html = admin_client.get(reverse("admin:catalog_product_changelist")).content.decode()
        assert '<html lang="ka"' in html

    def test_switches_to_english_with_the_language_cookie(self, admin_en):
        html = admin_en.get(reverse("admin:catalog_product_changelist")).content.decode()
        assert '<html lang="en"' in html

    def test_header_offers_the_language_switch(self, admin_client):
        html = admin_client.get(reverse("admin:index")).content.decode()
        assert "/i18n/setlang/" in html

    @pytest.mark.skipif(not KA_MO.exists(), reason="run `scripts/i18n.py compile` first")
    def test_catalog_labels_are_georgian(self, admin_client):
        html = admin_client.get(reverse("admin:catalog_product_add")).content.decode()
        assert "ერთადერთი ეგზემპლარი" in html  # "one of a kind"
        assert "ფოტოების დამატება" in html  # "Add photos"


def test_editor_offers_only_formatting_the_sanitiser_keeps(admin_client):
    html = admin_client.get(reverse("admin:catalog_product_add")).content.decode()
    for kept in ("bold", "italic", "heading3", "bullet", "number"):
        assert f'data-trix-attribute="{kept}"' in html
    for dropped in ("underlined", "strike", "heading1", "heading2", "heading4", "quote", "code"):
        assert f'data-trix-attribute="{dropped}"' not in html


def test_delivery_option_price_in_lari(admin_client):
    option = DeliveryOption.objects.create(code="x", name_ka="x", price=550)
    html = admin_client.get(
        reverse("admin:orders_deliveryoption_change", args=[option.pk])
    ).content.decode()
    assert 'value="5.50"' in html
