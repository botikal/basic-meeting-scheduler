"""Business hours in one timezone, shown to clients in another."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db

UTC = ZoneInfo("UTC")


@pytest.fixture
def seoul_hours(_scheduler_settings, settings):
    settings.SCHEDULER = {
        **settings.SCHEDULER,
        "BUSINESS_TIMEZONE": "Asia/Seoul",
        "DISPLAY_TIMEZONE": "UTC",
        "BUSINESS_START_HOUR": 9,
        "BUSINESS_END_HOUR": 18,
    }


def _next_weekday(offset: int = 3):
    day = (timezone.now() + timedelta(days=offset)).date()
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def test_slots_are_korean_working_hours_shown_in_utc(client, seoul_hours):
    day = _next_weekday()
    slots = client.get("/api/slots/", {"day": day.isoformat()}).json()["slots"]

    # 09:00-18:00 Asia/Seoul == 00:00-09:00 UTC, so the last start is 08:30
    first = datetime.fromisoformat(slots[0]).astimezone(UTC)
    last = datetime.fromisoformat(slots[-1]).astimezone(UTC)
    assert first.strftime("%H:%M") == "00:00"
    assert last.strftime("%H:%M") == "08:30"
    assert all(datetime.fromisoformat(s).astimezone(UTC).date() == day for s in slots)


def test_booking_page_says_utc(client, seoul_hours):
    assert "times shown in UTC" in client.get("/").content.decode()


def test_can_book_a_korean_morning_slot(client, seoul_hours):
    day = _next_weekday()
    start = datetime(day.year, day.month, day.day, 1, 0, tzinfo=UTC)  # 10:00 KST
    resp = client.post(
        "/book/",
        {
            "client_name": "Global Client",
            "client_email": "gc@example.com",
            "start": start.isoformat(),
            "note": "",
        },
    )
    assert resp.status_code == 302
