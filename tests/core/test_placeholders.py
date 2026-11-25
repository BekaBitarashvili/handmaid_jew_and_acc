import io

from PIL import Image

from apps.core import placeholders


def opened(content_file):
    return Image.open(io.BytesIO(content_file.read()))


def test_sizes_and_formats():
    assert opened(placeholders.product_photo("#C8862A", 1, "p.jpg")).size == (1600, 1600)
    assert opened(placeholders.category_tile("bracelet", 2, "t.jpg")).size == (1600, 1600)
    assert opened(placeholders.hero_image(0, "h.jpg")).size == (2400, 1050)
    assert opened(placeholders.banner_image("b.jpg")).format == "JPEG"


def test_warm_tones():
    # Average colour leans warm (red >= green >= blue), like the linen / umber palette.
    for image in (
        opened(placeholders.product_photo("#3FA9A0", 3, "p.jpg")),
        opened(placeholders.hero_image(1, "h.jpg")),
    ):
        r, g, b = image.resize((1, 1)).getpixel((0, 0))
        assert r >= g >= b
