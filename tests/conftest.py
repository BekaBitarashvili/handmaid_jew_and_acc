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
