import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.services.products import next_sku, prepare_product_for_save
from apps.catalog.services.slugs import fill_translated_slugs
from apps.catalog.signals import SkuChangeError

from .factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db
YEAR = timezone.localdate().year


class TestSku:
    def test_format_and_sequence_per_category(self):
        necklaces = CategoryFactory(code="NEC")
        earrings = CategoryFactory(code="EAR")
        assert next_sku(necklaces) == f"NEC-{YEAR}-0001"
        assert next_sku(necklaces) == f"NEC-{YEAR}-0002"
        assert next_sku(earrings) == f"EAR-{YEAR}-0001"

    def test_assigned_on_creation(self):
        product = ProductFactory(category=CategoryFactory(code="BRA"))
        assert product.sku == f"BRA-{YEAR}-0001"

    def test_manual_sku_on_creation_is_kept(self):
        product = ProductFactory(sku="OLD-0042")
        assert product.sku == "OLD-0042"

    def test_never_changes_when_category_changes(self):
        product = ProductFactory(category=CategoryFactory(code="NEC"))
        original = product.sku
        product.category = CategoryFactory(code="VIN")
        prepare_product_for_save(product, is_new=False)
        product.save()
        product.refresh_from_db()
        assert product.sku == original

    def test_direct_change_is_refused(self):
        product = ProductFactory()
        reloaded = Product.objects.get(pk=product.pk)
        reloaded.sku = "HACK-0001"
        with pytest.raises(SkuChangeError):
            reloaded.save()
        product.refresh_from_db()
        assert product.sku != "HACK-0001"


class TestSlugs:
    def test_georgian_is_transliterated_and_english_comes_from_english_name(self):
        product = ProductFactory(name_ka="ქარვის ყელსაბამი", name_en="Amber necklace")
        assert product.slug_ka == "karvis-qelsabami"
        assert product.slug_en == "amber-necklace"

    def test_english_falls_back_to_georgian_slug(self):
        product = ProductFactory(name_ka="ლაჟვარდის სამაჯური", name_en="")
        assert product.slug_en == product.slug_ka == "lazhvardis-samajuri"

    def test_duplicates_get_a_number(self):
        first = ProductFactory(name_ka="ქარვა", name_en="Amber")
        second = ProductFactory(name_ka="ქარვა", name_en="Amber")
        assert (first.slug_ka, second.slug_ka) == ("karva", "karva-2")
        assert (first.slug_en, second.slug_en) == ("amber", "amber-2")

    def test_typed_slug_is_normalised(self):
        category = CategoryFactory.build(code="QQQ", name_ka="x", name_en="x")
        category.slug_ka = "ჩემი სლაგი"
        category.slug_en = "My Slug!"
        fill_translated_slugs(category)
        assert (category.slug_ka, category.slug_en) == ("chemi-slagi", "my-slug")

    def test_resaving_keeps_own_slug(self):
        product = ProductFactory(name_ka="ქარვა", name_en="Amber")
        prepare_product_for_save(product, is_new=False)
        assert product.slug_ka == "karva"
