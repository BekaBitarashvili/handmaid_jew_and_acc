import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core.context_processors import site_settings
from apps.core.models import SiteSettings

pytestmark = pytest.mark.django_db


def test_load_creates_singleton_with_placeholder_brand():
    settings_obj = SiteSettings.load()
    assert settings_obj.pk == SiteSettings.SINGLETON_PK
    assert settings_obj.brand_name == "{{BRAND}}"
    assert SiteSettings.load().pk == settings_obj.pk
    assert SiteSettings.objects.count() == 1


def test_save_always_targets_the_singleton_row():
    SiteSettings.load()
    SiteSettings(brand_name="Other").save()
    assert SiteSettings.objects.count() == 1
    assert SiteSettings.load().brand_name == "Other"


def test_cannot_delete():
    with pytest.raises(RuntimeError):
        SiteSettings.load().delete()


def test_announcement_bar_is_translated(en):
    obj = SiteSettings.load()
    obj.announcement_bar_ka = "უფასო მიწოდება"
    obj.announcement_bar_en = ""
    obj.save()
    # Empty English falls back to Georgian (SPEC §3).
    assert SiteSettings.load().announcement_bar == "უფასო მიწოდება"


def test_context_processor_is_lazy(django_assert_num_queries):
    SiteSettings.load()
    request = RequestFactory().get("/")
    with django_assert_num_queries(0):
        context = site_settings(request)
    with django_assert_num_queries(1):
        assert context["site_settings"].brand_name == "{{BRAND}}"


def test_gel_template_filter(en):
    rendered = Template("{% load money %}{{ price|gel }}").render(Context({"price": 14500}))
    assert rendered == "145 ₾"
