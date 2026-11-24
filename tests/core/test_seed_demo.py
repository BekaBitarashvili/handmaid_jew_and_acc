from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

from apps.core.models import SiteSettings

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug(settings):
    settings.DEBUG = True


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
