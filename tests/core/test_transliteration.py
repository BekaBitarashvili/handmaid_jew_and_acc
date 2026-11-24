import pytest

from apps.core.transliteration import slugify_ka, transliterate


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("ქარვა", "karva"),
        ("ხელნაკეთი სამკაულები", "khelnaketi-samkaulebi"),
        ("ბუნებრივი ქვებით", "bunebrivi-kvebit"),
        ("ვერცხლი 925", "vertskhli-925"),
        ("ჟღალი ყელსაბამი", "zhghali-qelsabami"),
        ("ჭიკჭიკა წყალი", "chikchika-tsqali"),
        ("Amber ქარვა", "amber-karva"),
        ("ᲥᲐᲠᲕᲐ", "karva"),  # Mtavruli capitals
        ("  ქარვა!! — ბეჭედი  ", "karva-bechedi"),
    ],
)
def test_slugify_ka(text, slug):
    assert slugify_ka(text) == slug


def test_all_33_letters_are_mapped():
    alphabet = "აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰ"
    assert len(alphabet) == 33
    assert transliterate(alphabet).isascii()


def test_non_georgian_text_is_untouched():
    assert transliterate("Silver 925, glass") == "Silver 925, glass"
