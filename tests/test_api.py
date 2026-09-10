"""Tests for the JSON API."""

from datetime import timedelta

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def _book(api, slot, **overrides):
    payload = {
        "client_name": "Dana Client",
        "client_email": "dana@example.com",
        "start_at": slot.isoformat(),
    }
    payload.update(overrides)
    return api.post("/api/bookings/", payload, format="json")


def test_slots_lists_the_open_slot(api, slot):
    resp = api.get("/api/slots/", {"day": slot.date().isoformat()})
    assert resp.status_code == 200
    assert slot.isoformat() in resp.data["slots"]


def test_slots_requires_day(api):
    assert api.get("/api/slots/").status_code == 400


def test_booking_succeeds(api, slot):
    resp = _book(api, slot)
    assert resp.status_code == 201
    assert resp.data["status"] == "confirmed"
    assert resp.data["manage_url"].endswith(resp.data["manage_token"])


def test_double_booking_is_rejected(api, slot):
    assert _book(api, slot).status_code == 201
    assert _book(api, slot, client_email="other@example.com").status_code == 409


def test_booked_slot_leaves_availability(api, slot):
    _book(api, slot)
    resp = api.get("/api/slots/", {"day": slot.date().isoformat()})
    assert slot.isoformat() not in resp.data["slots"]


def test_unaligned_slot_is_rejected(api, slot):
    bad = slot.replace(minute=7).isoformat()
    assert _book(api, slot, start_at=bad).status_code == 409


def test_reschedule_moves_booking(api, slot, other_slot):
    token = _book(api, slot).data["manage_token"]
    resp = api.post(
        f"/api/bookings/{token}/reschedule/",
        {"start_at": other_slot.isoformat()},
        format="json",
    )
    assert resp.status_code == 200

    open_slots = api.get("/api/slots/", {"day": slot.date().isoformat()}).data["slots"]
    assert slot.isoformat() in open_slots
    assert other_slot.isoformat() not in open_slots


def test_cancel_frees_slot_and_blocks_changes(api, slot, other_slot):
    token = _book(api, slot).data["manage_token"]

    cancelled = api.post(f"/api/bookings/{token}/cancel/")
    assert cancelled.status_code == 200
    assert cancelled.data["status"] == "cancelled"

    open_slots = api.get("/api/slots/", {"day": slot.date().isoformat()}).data["slots"]
    assert slot.isoformat() in open_slots

    again = api.post(
        f"/api/bookings/{token}/reschedule/",
        {"start_at": other_slot.isoformat()},
        format="json",
    )
    assert again.status_code == 409


def test_booking_an_hour_spans_two_slots(api, slot):
    resp = _book(api, slot, slot_count=2)
    assert resp.status_code == 201
    assert resp.data["slot_count"] == 2

    token = resp.data["manage_token"]
    detail = api.get(f"/api/bookings/{token}/").data
    assert detail["end_at"][11:16] == (slot + timedelta(hours=1)).isoformat()[11:16]


def test_slots_slot_count_filter_excludes_starts_without_room(api, slot, next_slot):
    _book(api, next_slot)  # 30-minute booking in the second half of the hour

    day = slot.date().isoformat()
    one = api.get("/api/slots/", {"day": day, "slot_count": 1}).data["slots"]
    two = api.get("/api/slots/", {"day": day, "slot_count": 2}).data["slots"]
    assert slot.isoformat() in one
    assert slot.isoformat() not in two


def test_cannot_book_two_slots_when_the_second_is_taken(api, slot, next_slot):
    assert _book(api, next_slot).status_code == 201
    assert _book(api, slot, slot_count=2, client_email="c@d.com").status_code == 409


def test_unknown_token_is_404(api):
    assert api.get("/api/bookings/nope/").status_code == 404
