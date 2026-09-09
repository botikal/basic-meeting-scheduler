"""End-to-end tests for the booking API."""

from datetime import timedelta


def _book(client, slot, **overrides):
    payload = {
        "client_name": "Dana Client",
        "client_email": "dana@example.com",
        "start_at": slot.isoformat(),
        "note": "",
    }
    payload.update(overrides)
    return client.post("/api/bookings", json=payload)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_slots_lists_the_open_slot(client, slot):
    resp = client.get("/api/slots", params={"day": slot.date().isoformat()})
    assert resp.status_code == 200
    assert slot.isoformat() in resp.json()["slots"]


def test_booking_succeeds_and_returns_manage_link(client, slot):
    resp = _book(client, slot)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["manage_token"]
    assert body["manage_url"].endswith(body["manage_token"])


def test_double_booking_is_rejected(client, slot):
    assert _book(client, slot).status_code == 201
    second = _book(client, slot, client_email="someone@else.com")
    assert second.status_code == 409


def test_booked_slot_disappears_from_availability(client, slot):
    _book(client, slot)
    resp = client.get("/api/slots", params={"day": slot.date().isoformat()})
    assert slot.isoformat() not in resp.json()["slots"]


def test_unaligned_slot_is_rejected(client, slot):
    bad = (slot + timedelta(minutes=7)).isoformat()
    assert _book(client, slot, start_at=bad).status_code == 409


def test_past_slot_is_rejected(client, slot):
    past = (slot - timedelta(days=400)).isoformat()
    assert _book(client, slot, start_at=past).status_code == 409


def test_reschedule_moves_the_booking(client, slot, other_slot):
    token = _book(client, slot).json()["manage_token"]
    resp = client.post(
        f"/api/bookings/{token}/reschedule",
        json={"start_at": other_slot.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["start_at"].startswith(other_slot.isoformat())

    day = slot.date().isoformat()
    open_slots = client.get("/api/slots", params={"day": day}).json()["slots"]
    assert slot.isoformat() in open_slots  # freed up
    assert other_slot.isoformat() not in open_slots  # now taken


def test_cancel_frees_the_slot_and_blocks_further_changes(client, slot, other_slot):
    token = _book(client, slot).json()["manage_token"]

    cancelled = client.post(f"/api/bookings/{token}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    open_slots = client.get("/api/slots", params={"day": slot.date().isoformat()}).json()["slots"]
    assert slot.isoformat() in open_slots

    again = client.post(
        f"/api/bookings/{token}/reschedule", json={"start_at": other_slot.isoformat()}
    )
    assert again.status_code == 409


def test_unknown_token_is_404(client):
    assert client.get("/api/bookings/does-not-exist").status_code == 404


def test_admin_requires_auth(client):
    assert client.get("/api/admin/bookings").status_code == 401


def test_admin_lists_all_bookings(client, slot, other_slot):
    _book(client, slot)
    _book(client, other_slot, client_email="second@example.com")
    resp = client.get("/api/admin/bookings", auth=("admin", "secret"))
    assert resp.status_code == 200
    assert len(resp.json()) == 2
