"""Terms and Privacy exist from the start: checkout links to them. The text stays empty —
the owner provides it (with a lawyer); the page says so until then."""

from django.db import migrations

PAGES = [
    ("terms", "წესები და პირობები", "Terms and conditions"),
    ("privacy", "კონფიდენციალურობის პოლიტიკა", "Privacy policy"),
]


def create(apps, schema_editor):
    Page = apps.get_model("pages", "Page")
    for key, title_ka, title_en in PAGES:
        Page.objects.get_or_create(
            key=key, defaults={"title": title_ka, "title_ka": title_ka, "title_en": title_en}
        )


class Migration(migrations.Migration):
    dependencies = [("pages", "0002_page")]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
