from unittest import mock

import pytest
from django.db import OperationalError

pytestmark = pytest.mark.django_db


def test_healthz_ok(client):
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "no-cache" in response["Cache-Control"]


def test_healthz_reports_database_failure(client):
    with mock.patch("apps.core.views.connection.cursor", side_effect=OperationalError):
        response = client.get("/healthz/")
    assert response.status_code == 503


def test_healthz_rejects_post(client):
    assert client.post("/healthz/").status_code == 405
