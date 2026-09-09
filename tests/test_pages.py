"""Tests for the server-rendered booking pages."""

import pytest

from scheduling.models import Booking

pytestmark = pytest.mark.django_db


def test_index_loads(client):
    assert client.get("/").status_code == 200


def test_index_shows_slots_for_a_day(client, slot):
    resp = client.get("/", {"day": slot.date().isoformat()})
    assert resp.status_code == 200
    assert slot.isoformat() in resp.content.decode()


def test_full_booking_flow(client, slot):
    day = slot.date().isoformat()
    resp = client.post(
        "/book/",
        {
            "day": day,
            "start_at": slot.isoformat(),
            "client_name": "Dana Client",
            "client_email": "dana@example.com",
            "note": "First call",
        },
    )
    assert resp.status_code == 302

    booking = Booking.objects.get()
    assert booking.client_name == "Dana Client"
    assert booking.status == Booking.Status.CONFIRMED
    assert resp.url == f"/b/{booking.manage_token}/"

    # manage page renders and offers a cancel button
    manage = client.get(resp.url)
    assert manage.status_code == 200
    assert "Cancel booking" in manage.content.decode()


def test_cannot_book_a_taken_slot_via_page(client, slot):
    day = slot.date().isoformat()
    form = {
        "day": day,
        "start_at": slot.isoformat(),
        "client_name": "First",
        "client_email": "first@example.com",
        "note": "",
    }
    assert client.post("/book/", form).status_code == 302

    # second attempt at the same slot: the choice is gone, so the form re-renders
    resp = client.post("/book/", {**form, "client_email": "second@example.com"})
    assert resp.status_code == 200
    assert Booking.objects.count() == 1


def test_cancel_via_page(client, slot):
    client.post(
        "/book/",
        {
            "day": slot.date().isoformat(),
            "start_at": slot.isoformat(),
            "client_name": "Dana",
            "client_email": "dana@example.com",
            "note": "",
        },
    )
    booking = Booking.objects.get()
    resp = client.post(f"/b/{booking.manage_token}/cancel/")
    assert resp.status_code == 302
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_admin_requires_login(client):
    resp = client.get("/admin/")
    assert resp.status_code == 302
    assert "/login" in resp.url
