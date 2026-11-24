from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.fields import GelFormField
from apps.core.sanitize import clean_html


class TestGelFormField:
    @pytest.mark.parametrize(("typed", "tetri"), [("145", 14500), ("145.50", 14550), ("0.5", 50)])
    def test_lari_in_tetri_out(self, typed, tetri):
        assert GelFormField().clean(typed) == tetri

    @pytest.mark.parametrize("typed", ["1.005", "-1", "abc"])
    def test_invalid(self, typed):
        with pytest.raises(ValidationError):
            GelFormField().clean(typed)

    def test_displays_lari(self):
        field = GelFormField()
        assert field.prepare_value(14500) == Decimal("145")
        assert field.prepare_value(14550) == Decimal("145.50")

    def test_optional_empty(self):
        assert GelFormField(required=False).clean("") is None


class TestCleanHtml:
    def test_keeps_allowed_formatting(self):
        html = "<h3>Story</h3><p><strong>Amber</strong> <em>and</em> silver</p><ul><li>a</li></ul>"
        assert clean_html(html) == html

    def test_removes_scripts_styles_and_attributes(self):
        dirty = '<p onclick="x()" style="color:red">Hi<script>alert(1)</script></p><img src=x>'
        assert clean_html(dirty) == "<p>Hi</p>"

    def test_editor_markup_is_mapped(self):
        assert clean_html("<div><b>Bold</b> <i>it</i></div><h1>T</h1>") == (
            "<p><strong>Bold</strong> <em>it</em></p><h3>T</h3>"
        )

    def test_javascript_links_lose_their_href(self):
        cleaned = clean_html('<a href="javascript:alert(1)">x</a>')
        assert "javascript" not in cleaned

    def test_links_get_safe_rel(self):
        assert 'rel="noopener noreferrer"' in clean_html('<a href="https://x.ge">x</a>')

    def test_rich_text_field_sanitises_on_save(self, db):
        from tests.catalog.factories import StoneFactory

        stone = StoneFactory(story_ka="<p>ok</p><script>bad()</script>")
        stone.refresh_from_db()
        assert stone.story_ka == "<p>ok</p>"
