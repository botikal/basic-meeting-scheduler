"""Tests for the server-rendered booking flow."""

import pytest

from scheduling.models import Booking

pytestmark = pytest.mark.django_db


def _details(**overrides):
    data = {
        "client_name": "Dana Client",
        "client_email": "dana@example.com",
        "note": "",
    }
    data.update(overrides)
    return data


def test_index_shows_calendar(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="planner"' in resp.content.decode()


def test_picking_a_day_shows_slot_times(client, slot):
    resp = client.get("/", {"date": slot.date().isoformat()})
    body = resp.content.decode()
    assert resp.status_code == 200
    assert slot.strftime("%H:%M") in body


def test_picking_a_slot_shows_the_details_form(client, slot):
    resp = client.get("/", {"date": slot.date().isoformat(), "start": slot.isoformat()})
    assert resp.status_code == 200
    assert "Your name" in resp.content.decode()


def test_htmx_request_returns_only_the_planner_partial(client):
    resp = client.get("/", headers={"HX-Request": "true"})
    body = resp.content.decode()
    assert resp.status_code == 200
    assert 'id="planner"' in body
    assert "<html" not in body


def test_full_booking_flow(client, slot):
    resp = client.post("/book/", _details(start=slot.isoformat()))
    assert resp.status_code == 302

    booking = Booking.objects.get()
    assert booking.client_name == "Dana Client"
    assert booking.status == Booking.Status.CONFIRMED
    assert resp.url == f"/b/{booking.manage_token}/"

    manage = client.get(resp.url)
    assert manage.status_code == 200
    assert "Cancel booking" in manage.content.decode()


def test_htmx_booking_redirects_via_header(client, slot):
    resp = client.post("/book/", _details(start=slot.isoformat()), headers={"HX-Request": "true"})
    assert resp.status_code == 204
    assert resp["HX-Redirect"].startswith("/b/")


def test_double_booking_via_page_is_blocked(client, slot):
    assert client.post("/book/", _details(start=slot.isoformat())).status_code == 302

    resp = client.post(
        "/book/", _details(start=slot.isoformat(), client_email="second@example.com")
    )
    assert resp.status_code == 200  # re-rendered with an error
    assert Booking.objects.count() == 1


def test_missing_details_re_renders_form(client, slot):
    resp = client.post("/book/", {"start": slot.isoformat(), "client_name": "Only Name"})
    assert resp.status_code == 200
    assert Booking.objects.count() == 0


def test_reschedule_flow(client, slot, other_slot):
    client.post("/book/", _details(start=slot.isoformat()))
    booking = Booking.objects.get()

    resp = client.post(f"/b/{booking.manage_token}/reschedule/", {"start": other_slot.isoformat()})
    assert resp.status_code == 302
    booking.refresh_from_db()
    assert booking.start_at == other_slot


def test_cancel_flow(client, slot):
    client.post("/book/", _details(start=slot.isoformat()))
    booking = Booking.objects.get()

    resp = client.post(f"/b/{booking.manage_token}/cancel/")
    assert resp.status_code == 302
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_unknown_token_is_404(client):
    assert client.get("/b/nope/").status_code == 404


def test_admin_requires_login(client):
    resp = client.get("/admin/")
    assert resp.status_code == 302
    assert "/login" in resp.url
