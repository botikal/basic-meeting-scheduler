"""Tests for the "find my meeting" lookup (no accounts - just an email)."""

import pytest

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


def test_find_page_renders(client):
    resp = client.get("/find/")
    assert resp.status_code == 200
    assert "Find your meeting" in resp.content.decode()


def test_find_shows_confirmed_bookings(client, slot):
    _booking(slot)
    body = client.post("/find/", {"email": "dana@example.com"}).content.decode()
    assert "View / manage" in body


def test_find_excludes_cancelled_bookings(client, slot):
    cancel_booking(_booking(slot))
    body = client.post("/find/", {"email": "dana@example.com"}).content.decode()
    assert "No meetings found" in body
    assert "View / manage" not in body


def test_find_says_nothing_for_an_unknown_email(client):
    body = client.post("/find/", {"email": "nobody@example.com"}).content.decode()
    assert "No meetings found" in body


def test_find_has_a_back_link(client):
    resp = client.get("/find/")
    assert 'href="/"' in resp.content.decode()
