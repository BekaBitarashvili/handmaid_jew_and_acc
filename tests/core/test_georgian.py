import pytest
from django.db.models import fields as model_fields
from django.template import Context, Template
from django.utils import text
from django.utils.translation import gettext_lazy

from apps.catalog.models import Product


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ერთადერთი ეგზემპლარი", "ერთადერთი ეგზემპლარი"),  # Mkhedruli stays as is
        ("one of a kind", "One of a kind"),
        ("SEO სათაური", "SEO სათაური"),
        ("", ""),
    ],
)
def test_capfirst_keeps_georgian_lowercase(value, expected):
    assert text.capfirst(value) == expected


def test_python_would_produce_mtavruli():
    # The reason for the patch: Unicode 11 maps Mkhedruli to Mtavruli capitals.
    assert "ე".upper() == "Ე"


def test_lazy_strings_still_work():
    assert str(text.capfirst(gettext_lazy("price"))) in ("Price", "ფასი")


def test_modules_that_imported_capfirst_early_are_patched():
    assert model_fields.capfirst is text.capfirst


def test_model_form_label(ka):
    label = Product._meta.get_field("is_unique").formfield().label
    assert not any("Ა" <= ch <= "Ჿ" for ch in str(label))


def test_template_filter():
    rendered = Template("{{ a|capfirst }} {{ b|capfirst }}").render(
        Context({"a": "ქარვა", "b": "amber"})
    )
    assert rendered == "ქარვა Amber"
