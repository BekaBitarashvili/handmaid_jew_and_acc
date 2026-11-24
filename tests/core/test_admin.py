import pytest
from django.urls import reverse

from apps.core.models import SiteSettings

pytestmark = pytest.mark.django_db


def test_changelist_redirects_to_singleton(admin_client):
    response = admin_client.get(reverse("admin:core_sitesettings_changelist"))
    assert response.status_code == 302
    assert response.url == reverse("admin:core_sitesettings_change", args=[1])


def test_change_page_renders_with_translation_fields(admin_client):
    SiteSettings.load()
    response = admin_client.get(reverse("admin:core_sitesettings_change", args=[1]))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="announcement_bar_ka"' in content
    assert 'name="announcement_bar_en"' in content


def test_cannot_add_or_delete(admin_client):
    SiteSettings.load()
    assert admin_client.get(reverse("admin:core_sitesettings_add")).status_code == 403
    assert admin_client.get(reverse("admin:core_sitesettings_delete", args=[1])).status_code == 403


def test_admin_lives_at_admin_url_not_default(client, settings):
    assert settings.ADMIN_URL != "admin/"
    assert client.get("/admin/").status_code == 404
