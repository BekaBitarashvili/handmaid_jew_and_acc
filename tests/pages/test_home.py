from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone
from django.utils.translation import override

from apps.catalog.models import Product
from apps.core.models import SiteSettings
from apps.pages.models import HeroSlide, localized_link
from apps.promotions.models import Sale
from tests.catalog.factories import CategoryFactory, ProductFactory, ProductImageFactory, make_jpeg

pytestmark = pytest.mark.django_db
ACTIVE = Product.Status.ACTIVE


def home(client) -> str:
    response = client.get("/en/")
    assert response.status_code == 200
    return response.content.decode()


def slide(title, order=0, **extra):
    return HeroSlide.objects.create(
        image=make_jpeg(size=(1600, 700), name="hero.jpg"),
        title_en=title,
        title_ka=title,
        sort_order=order,
        **extra,
    )


class TestHero:
    def test_slides_in_order_with_counter_and_localized_buttons(self, client, en):
        slide("Second", order=2)
        slide(
            "First",
            order=1,
            primary_text_en="Shop Now",
            primary_link="/shop/",
            secondary_text_en="Explore",
            secondary_link="https://example.com/x",
        )
        slide("Hidden", is_active=False)
        html = home(client)
        assert html.index("First") < html.index("Second")
        assert "Hidden" not in html
        assert "01 / 02" in html
        assert 'href="/en/shop/" class="btn btn-light">Shop Now' in html
        assert 'href="https://example.com/x"' in html

    def test_no_autoplay_anywhere(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "site.js").read_text(encoding="utf-8")
        assert "setInterval" not in js and "autoplay" not in js.lower().replace("no autoplay", "")

    def test_localized_link(self):
        with override("ka"):
            assert localized_link("/shop/new/") == "/ka/shop/new/"
            assert localized_link("/en/shop/") == "/en/shop/"
            assert localized_link("https://x.ge/") == "https://x.ge/"
            assert localized_link("") == ""


class TestSections:
    def test_category_tiles_chosen_and_ordered(self, client, en):
        CategoryFactory(name_en="Second tile", show_on_home=True, home_order=2)
        CategoryFactory(name_en="First tile", show_on_home=True, home_order=1)
        CategoryFactory(name_en="Not a tile", show_on_home=False)
        for i in range(3):
            CategoryFactory(name_en=f"Extra {i}", show_on_home=True, home_order=10 + i)
        html = home(client)
        assert html.index("First tile") < html.index("Second tile")
        assert "Not a tile" not in html.split("<footer")[0].split('aria-label="Categories"')[1]
        assert "Extra 2" not in html.split('aria-label="Categories"')[1].split("</section>")[0]

    def test_new_arrivals_up_to_four_new_pieces(self, client, en):
        for i in range(5):
            ProductFactory(status=ACTIVE, name_en=f"Newbie {i}", published_at=timezone.now())
        ProductFactory(status=ACTIVE, name_en="Old one", new_badge=Product.NewBadge.NO)
        section = home(client).split('id="new-title"')[1].split("</section>")[0]
        assert section.count("<article") == 4
        assert "Old one" not in section
        assert 'href="/en/shop/new/"' in home(client)

    def test_intro_text_only_when_set(self, client, en):
        assert "A line from the owner" not in home(client)
        site = SiteSettings.load()
        site.intro_text_en = "A line from the owner"
        site.save()
        assert "A line from the owner" in home(client)

    def test_organization_schema(self, client, en):
        assert '"@type":"Organization"' in home(client)


class TestOffersBanner:
    def make_sale(self, **extra):
        sale = Sale.objects.create(
            name="Banner sale",
            percent=30,
            show_on_home=True,
            banner_title_en="Special Offers",
            banner_subtitle_en="Selected items at 30% off",
            **extra,
        )
        return sale

    def test_hidden_without_a_running_home_sale(self, client, en):
        ProductFactory(status=ACTIVE)
        assert 'id="offers-title"' not in home(client)
        sale = self.make_sale(is_active=False)
        sale.products.set(Product.objects.all())
        assert 'id="offers-title"' not in home(client)

    def test_shows_a_real_discounted_piece(self, client, en):
        product = ProductFactory(status=ACTIVE, price=12000)
        ProductImageFactory(product=product)
        self.make_sale().products.set([product])
        html = home(client)
        banner = html.split('id="offers-title"')[1].split("</section>")[0]
        assert "Selected items at 30% off" in banner
        assert "120" in banner and "84" in banner and "−30%" in banner
        assert f'href="{product.get_absolute_url()}"' in banner
        assert 'href="/en/shop/sale/"' in banner

    def test_hidden_when_nothing_in_the_sale_is_listed(self, client, en):
        sold = ProductFactory(status=Product.Status.SOLD)
        self.make_sale().products.set([sold])
        assert 'id="offers-title"' not in home(client)
