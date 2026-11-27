from datetime import datetime
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.phones import format_phone, normalize_phone
from apps.orders.numbers import next_order_number

pytestmark = pytest.mark.django_db


def at(year):
    return mock.patch(
        "apps.orders.numbers.timezone.localdate",
        return_value=datetime(year, 6, 1, tzinfo=timezone.get_current_timezone()).date(),
    )


class TestOrderNumbers:
    def test_yy_dash_counter_from_1001(self):
        with at(2026):
            assert [next_order_number() for _ in range(3)] == ["26-1001", "26-1002", "26-1003"]

    def test_counter_restarts_each_year(self):
        with at(2026):
            next_order_number()
            next_order_number()
        with at(2027):
            assert next_order_number() == "27-1001"
        with at(2026):
            assert next_order_number() == "26-1003"


class TestPhones:
    @pytest.mark.parametrize(
        "raw",
        ["555 12 34 56", "555123456", "+995 555 123 456", "995555123456", "+995-555-12-34-56"],
    )
    def test_georgian_mobile_forms(self, raw):
        assert normalize_phone(raw) == "+995555123456"

    def test_tbilisi_landline(self):
        assert normalize_phone("032 2 12 34 56") == "+995322123456"

    def test_buyer_abroad(self):
        assert normalize_phone("+49 30 12345678") == "+493012345678"

    @pytest.mark.parametrize("raw", ["", "12", "hello", "+995 555"])
    def test_invalid(self, raw):
        with pytest.raises(ValidationError):
            normalize_phone(raw)

    def test_recipient_must_be_georgian(self):
        assert normalize_phone("555123456", georgian_only=True) == "+995555123456"
        with pytest.raises(ValidationError) as error:
            normalize_phone("+49 30 12345678", georgian_only=True)
        assert error.value.code == "not_georgian"

    def test_display(self):
        assert format_phone("+995555123456") == "+995 555 12 34 56"
        assert format_phone("") == ""
