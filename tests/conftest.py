import pytest
from django.utils import translation


@pytest.fixture
def ka():
    with translation.override("ka"):
        yield


@pytest.fixture
def en():
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path):
    """Uploads and thumbnails go to a temp folder, never into media/."""
    settings.MEDIA_ROOT = tmp_path / "media"
