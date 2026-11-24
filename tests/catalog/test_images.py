import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.images import FORMATS, WIDTHS, admin_thumb, generate_all, rendition
from apps.catalog.services.images import InvalidImageError, process_upload

from .factories import ProductImageFactory, make_jpeg

GPS_IFD = 0x8825
ORIENTATION = 0x0112
MAKE = 0x010F


def exif_with_gps_and_rotation() -> Image.Exif:
    exif = Image.Exif()
    exif[ORIENTATION] = 6  # rotate 90° clockwise on display
    exif[MAKE] = "PhoneMaker"
    exif.get_ifd(GPS_IFD).update({1: "N", 2: (41.0, 43.0, 0.0), 3: "E", 4: (44.0, 47.0, 0.0)})
    return exif


class TestProcessUpload:
    def test_source_fixture_really_has_gps(self):
        with Image.open(make_jpeg(exif=exif_with_gps_and_rotation())) as image:
            assert image.getexif().get_ifd(GPS_IFD)

    def test_strips_all_metadata_including_gps(self):
        processed = process_upload(make_jpeg(exif=exif_with_gps_and_rotation()))
        with Image.open(io.BytesIO(processed.file.read())) as image:
            exif = image.getexif()
            assert not exif.get_ifd(GPS_IFD)
            assert len(exif) == 0

    def test_applies_phone_rotation(self):
        processed = process_upload(make_jpeg(size=(800, 600), exif=exif_with_gps_and_rotation()))
        assert (processed.width, processed.height) == (600, 800)

    def test_caps_long_side_and_flags_small_photos(self):
        big = process_upload(make_jpeg(size=(3000, 3750)))
        assert max(big.width, big.height) == 2400
        assert not big.below_recommended
        small = process_upload(make_jpeg(size=(800, 1000)))
        assert small.below_recommended

    def test_transparent_png_becomes_jpeg_on_ivory(self):
        processed = process_upload(make_jpeg(mode="RGBA", name="cut-out.png"))
        assert processed.file.name == "cut-out.jpg"
        with Image.open(io.BytesIO(processed.file.read())) as image:
            assert image.format == "JPEG"
            assert image.mode == "RGB"

    def test_rejects_non_images(self):
        with pytest.raises(InvalidImageError):
            process_upload(SimpleUploadedFile("notes.jpg", b"not an image"))


@pytest.mark.django_db
class TestRenditions:
    def test_generates_avif_and_webp_in_4_5(self):
        image = ProductImageFactory(image=make_jpeg(size=(1600, 2000)))
        assert generate_all(image.image) == len(FORMATS) * len(WIDTHS) + 1
        for fmt in FORMATS:
            r = rendition(image.image, 400, fmt)
            assert r.url.endswith(f".{fmt}")
            assert (r.width, r.height) == (400, 500)

    def test_never_upscales(self):
        image = ProductImageFactory(image=make_jpeg(size=(800, 1000)))
        assert rendition(image.image, 1800, "webp").width == 800

    def test_admin_thumbnail(self):
        image = ProductImageFactory()
        assert admin_thumb(image.image).width == 96
