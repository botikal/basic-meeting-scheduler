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


def test_calendar_marks_days_that_have_bookings(client, staff_user, slot):
    _booking(slot)
    client.force_login(staff_user)
    body = client.get("/staff/", {"month": slot.strftime("%Y-%m")}).content.decode()
    assert "cal-dot" in body


def test_calendar_has_no_dot_in_an_empty_month(client, staff_user):
    client.force_login(staff_user)
    body = client.get("/staff/", {"month": "2020-01"}).content.decode()
    assert "cal-dot" not in body


def test_clicking_a_day_lists_its_bookings(client, staff_user, slot):
    _booking(slot)
    client.force_login(staff_user)
    body = client.get("/staff/", {"date": slot.date().isoformat()}).content.decode()
    assert "Dana Client" in body
    assert "dana@example.com" in body


def test_empty_day_says_nothing_booked(client, staff_user, slot):
    client.force_login(staff_user)
    body = client.get("/staff/", {"date": slot.date().isoformat()}).content.decode()
    assert "Nothing booked" in body


def test_selected_day_shows_cancelled_bookings_too(client, staff_user, slot, next_slot):
    _booking(slot, client_name="Keep Me")
    cancel_booking(_booking(next_slot, client_name="Gone Away", client_email="g@h.com"))
    client.force_login(staff_user)

    body = client.get("/staff/", {"date": slot.date().isoformat()}).content.decode()
    assert "Keep Me" in body
    assert "Gone Away" in body
    assert "Cancelled" in body


def test_htmx_returns_the_calendar_partial(client, staff_user):
    client.force_login(staff_user)
    resp = client.get("/staff/", {"month": "2026-09"}, headers={"HX-Request": "true"})
    body = resp.content.decode()
    assert 'id="staff-cal"' in body
    assert "<html" not in body


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
