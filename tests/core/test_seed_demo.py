from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

from apps.core.models import SiteSettings

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug(settings):
    settings.DEBUG = True


@pytest.fixture(autouse=True)
def fast_placeholders(monkeypatch):
    """Full-size placeholder photos take seconds each; their look is tested separately."""
    from tests.catalog.factories import make_jpeg

    def tiny(*args, **kwargs):
        return make_jpeg(size=(40, 40), name="demo.jpg")

    for target in (
        "apps.catalog.seed.product_photo",
        "apps.catalog.seed.category_tile",
        "apps.pages.seed.hero_image",
        "apps.promotions.seed.banner_image",
    ):
        monkeypatch.setattr(target, tiny)


@pytest.fixture
def superuser_env(monkeypatch):
    monkeypatch.setenv("DEV_SUPERUSER_USERNAME", "owner")
    monkeypatch.setenv("DEV_SUPERUSER_EMAIL", "owner@example.com")
    monkeypatch.setenv("DEV_SUPERUSER_PASSWORD", "a-long-dev-password-123")


def run() -> str:
    out = StringIO()
    call_command("seed_demo", "--no-input", stdout=out)
    return out.getvalue()


def test_refuses_without_debug():
    with pytest.raises(CommandError, match="DEBUG"):
        run()


def test_creates_site_settings_and_superuser(debug, superuser_env):
    output = run()
    assert SiteSettings.objects.get().brand_name == "{{BRAND}}"
    user = get_user_model().objects.get(username="owner")
    assert user.is_superuser
    assert user.check_password("a-long-dev-password-123")
    assert "created 'owner'" in output


def test_is_idempotent_and_never_resets_password(debug, superuser_env, monkeypatch):
    run()
    monkeypatch.setenv("DEV_SUPERUSER_PASSWORD", "another-password-456")
    output = run()
    assert SiteSettings.objects.count() == 1
    assert get_user_model().objects.count() == 1
    assert get_user_model().objects.get().check_password("a-long-dev-password-123")
    assert "kept 'owner'" in output


def test_keeps_owner_edits_to_site_settings(debug, superuser_env):
    site = SiteSettings.load()
    site.brand_name = "Atelier"
    site.save()
    run()
    assert SiteSettings.load().brand_name == "Atelier"


def test_skips_superuser_without_password(debug, monkeypatch):
    monkeypatch.setenv("DEV_SUPERUSER_PASSWORD", "")
    output = run()
    assert "skipped" in output
    assert not get_user_model().objects.exists()


def test_seed_builds_home_content(debug, superuser_env):
    from apps.catalog.models import Category
    from apps.pages.models import HeroSlide
    from apps.promotions.models import Sale

    run()
    assert HeroSlide.objects.count() == 3
    assert Category.objects.filter(show_on_home=True).count() == 4
    sale = Sale.objects.get()
    assert sale.show_on_home and sale.percent == 30
    assert SiteSettings.load().intro_text_en


def test_reset_catalog_rebuilds(debug, superuser_env):
    from apps.catalog.models import Product

    run()
    first = set(Product.objects.values_list("pk", flat=True))
    call_command("seed_demo", "--no-input", "--reset-catalog", stdout=StringIO())
    assert Product.objects.count() == len(first)
    assert not first & set(Product.objects.values_list("pk", flat=True))
