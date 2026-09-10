"""Tests for the staff area."""

import pytest

from scheduling.models import Booking
from scheduling.services import cancel_booking, create_booking

pytestmark = pytest.mark.django_db


def _booking(slot, **overrides):
    data = {
        "client_name": "Dana Client",
        "client_email": "dana@example.com",
        "start_at": slot,
    }
    data.update(overrides)
    return create_booking(**data)


def test_staff_home_requires_login(client):
    resp = client.get("/staff/")
    assert resp.status_code == 302
    assert "/staff/login/" in resp.url


def test_non_staff_user_is_bounced(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("joe", password="pw"))
    resp = client.get("/staff/")
    assert resp.status_code == 302
    assert "/staff/login/" in resp.url


def test_login_page_renders(client):
    resp = client.get("/staff/login/")
    assert resp.status_code == 200
    assert "Staff login" in resp.content.decode()


def test_staff_sees_upcoming_bookings(client, staff_user, slot):
    _booking(slot)
    client.force_login(staff_user)

    body = client.get("/staff/").content.decode()
    assert "Dana Client" in body
    assert "dana@example.com" in body


def test_staff_can_cancel(client, staff_user, slot):
    booking = _booking(slot)
    client.force_login(staff_user)

    resp = client.post(f"/staff/b/{booking.manage_token}/cancel/")
    assert resp.status_code == 302
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_staff_cancel_rejects_get(client, staff_user, slot):
    booking = _booking(slot)
    client.force_login(staff_user)
    assert client.get(f"/staff/b/{booking.manage_token}/cancel/").status_code == 405


def test_upcoming_hides_cancelled_but_all_shows_it(client, staff_user, slot, other_slot):
    _booking(slot, client_name="Keep Me")
    cancel_booking(_booking(other_slot, client_name="Drop Me", client_email="d@e.com"))
    client.force_login(staff_user)

    upcoming = client.get("/staff/").content.decode()
    assert "Keep Me" in upcoming
    assert "Drop Me" not in upcoming

    everything = client.get("/staff/?all=1").content.decode()
    assert "Drop Me" in everything
