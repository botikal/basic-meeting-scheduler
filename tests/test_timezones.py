"""Business hours in one timezone, shown to clients in another."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import RequestFactory
from django.utils import timezone

from scheduling.services import create_booking
from scheduling.tzdetect import client_timezone

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


# --- Detecting the visitor's own timezone (client-side cookie) -------------


def test_client_timezone_reads_a_valid_cookie():
    request = RequestFactory().get("/")
    request.COOKIES["tz"] = "Europe/Paris"
    assert client_timezone(request) == "Europe/Paris"


def test_client_timezone_decodes_the_url_encoded_cookie_value():
    # base.html sets the cookie via encodeURIComponent (zone names contain
    # "/"), so the raw cookie value is percent-encoded - this is what Django's
    # request.COOKIES actually contains for a real browser request, unlike a
    # plain "Asia/Seoul" string set directly in a test.
    request = RequestFactory().get("/")
    request.COOKIES["tz"] = "Asia%2FSeoul"
    assert client_timezone(request) == "Asia/Seoul"


def test_client_timezone_is_none_without_a_cookie():
    assert client_timezone(RequestFactory().get("/")) is None


def test_client_timezone_ignores_a_bogus_value():
    request = RequestFactory().get("/")
    request.COOKIES["tz"] = "Not/AZone"
    assert client_timezone(request) is None


def test_booking_page_defaults_to_configured_timezone_without_a_cookie(client):
    assert "times shown in UTC" in client.get("/").content.decode()


def test_visitor_timezone_cookie_overrides_the_display_timezone(client):
    client.cookies["tz"] = "America/New_York"
    assert "times shown in America/New_York" in client.get("/").content.decode()


def test_a_bogus_timezone_cookie_falls_back_to_the_default(client):
    client.cookies["tz"] = "Not/AZone"
    assert "times shown in UTC" in client.get("/").content.decode()


def test_visitor_timezone_shifts_the_displayed_slot_times(client):
    # Default test settings: business hours 09:00-17:00 UTC (see conftest).
    day = _next_weekday()
    client.cookies["tz"] = "Asia/Seoul"  # UTC+9, no DST to worry about
    body = client.get("/", {"date": day.isoformat()}).content.decode()
    assert "18:00" in body  # 09:00 UTC == 18:00 KST


def test_client_facing_pages_are_never_cached(client, slot):
    """A browser must never serve a stale (pre-cookie) page from its HTTP
    cache on the tz-detection reload - the response has to say so explicitly,
    since cookies aren't part of the cache key by default."""
    booking = create_booking(
        client_name="Cache Check", client_email="cc@example.com", start_at=slot
    )
    for resp in (client.get("/"), client.get(f"/b/{booking.manage_token}/")):
        assert "no-store" in resp.headers["Cache-Control"]
