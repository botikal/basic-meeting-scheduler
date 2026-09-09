"""Shared fixtures for the scheduler tests."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

UTC = ZoneInfo("UTC")

TEST_SCHEDULER = {
    "HOST_NAME": "Acme Corp",
    "BASE_URL": "http://testserver",
    "TIMEZONE": "UTC",
    "BUSINESS_START_HOUR": 9,
    "BUSINESS_END_HOUR": 17,
    "SLOT_MINUTES": 30,
    "AVAILABLE_WEEKDAYS": [0, 1, 2, 3, 4],
    "BOOKING_HORIZON_DAYS": 60,
    "MIN_NOTICE_HOURS": 0,
}


@pytest.fixture(autouse=True)
def _scheduler_settings(settings):
    settings.SCHEDULER = dict(TEST_SCHEDULER)


def _weekday_at_nine(day_offset: int) -> datetime:
    day = (timezone.now() + timedelta(days=day_offset)).date()
    while day.weekday() not in TEST_SCHEDULER["AVAILABLE_WEEKDAYS"]:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)


@pytest.fixture
def slot() -> datetime:
    """A valid, bookable slot: an upcoming weekday at opening time."""
    return _weekday_at_nine(3)


@pytest.fixture
def other_slot(slot) -> datetime:
    """A second valid slot, one hour after `slot`."""
    return slot + timedelta(hours=1)
