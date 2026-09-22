"""Tests for the server-rendered booking flow."""

import pytest

from scheduling.availability import available_slots
from scheduling.models import Booking
from scheduling.rules import Rules

pytestmark = pytest.mark.django_db


def _details(**overrides):
    data = {
        "client_name": "Dana Client",
        "client_email": "dana@example.com",
        "note": "",
    }
    data.update(overrides)
    return data


def test_landing_page_lists_the_three_services(client):
    resp = client.get("/")
    body = resp.content.decode()
    assert resp.status_code == 200
    assert "Headhunting" in body
    assert "Japan services" in body
    assert "Wanted Global service introduction" in body
    assert 'href="/schedule/?service=japan"' in body


def test_landing_page_has_a_find_my_meeting_card(client):
    """Sized and styled the same as the three real service cards, not a
    smaller secondary button - see the comment in landing.html."""
    body = client.get("/").content.decode()
    assert 'class="service-card" href="/find/"' in body
    assert "Already booked?" in body


def test_footer_find_link_is_styled_bigger_everywhere(client):
    for resp in (client.get("/"), client.get("/find/")):
        assert 'class="foot-find"' in resp.content.decode()


def test_picking_a_service_carries_it_into_the_calendar(client, slot):
    resp = client.get(
        "/schedule/",
        {"service": "japan", "date": slot.date().isoformat(), "start": slot.isoformat()},
    )
    body = resp.content.decode()
    assert resp.status_code == 200
    assert "Japan services" in body
    assert 'name="service" value="japan"' in body


def test_an_unknown_service_is_dropped(client, slot):
    resp = client.get(
        "/schedule/",
        {
            "service": "not-a-real-service",
            "date": slot.date().isoformat(),
            "start": slot.isoformat(),
        },
    )
    assert 'name="service" value=""' in resp.content.decode()


def test_index_shows_calendar(client):
    resp = client.get("/schedule/")
    assert resp.status_code == 200
    assert 'id="planner"' in resp.content.decode()


def test_picking_a_day_shows_slot_times(client, slot):
    resp = client.get("/schedule/", {"date": slot.date().isoformat()})
    body = resp.content.decode()
    assert resp.status_code == 200
    assert slot.strftime("%H:%M") in body


def test_picking_a_slot_shows_the_details_form(client, slot):
    resp = client.get("/schedule/", {"date": slot.date().isoformat(), "start": slot.isoformat()})
    assert resp.status_code == 200
    assert "Your name" in resp.content.decode()


def test_confirm_booking_button_disables_itself_on_click(client, slot):
    """A double-click (or one impatient repeat click before the first
    response lands) must not fire the POST twice - the two requests would
    race server-side, and the loser comes back "That time was just taken"
    even though the winner - the same user's own first click - genuinely
    booked it. hx-disabled-elt stops the second request from ever being
    sent; see the comment above this button in _planner.html."""
    body = client.get(
        "/schedule/", {"date": slot.date().isoformat(), "start": slot.isoformat()}
    ).content.decode()
    assert 'hx-disabled-elt="this"' in body


def test_htmx_request_returns_only_the_planner_partial(client):
    resp = client.get("/schedule/", headers={"HX-Request": "true"})
    body = resp.content.decode()
    assert resp.status_code == 200
    assert 'id="planner"' in body
    assert "<html" not in body


def test_full_booking_flow(client, slot):
    resp = client.post("/schedule/book/", _details(start=slot.isoformat()))
    assert resp.status_code == 302

    booking = Booking.objects.get()
    assert booking.client_name == "Dana Client"
    assert booking.status == Booking.Status.CONFIRMED
    assert resp.url == f"/b/{booking.manage_token}/"

    manage = client.get(resp.url)
    assert manage.status_code == 200
    assert "Cancel booking" in manage.content.decode()


def test_booked_confirmation_shows_between_details_and_calendar(client, slot):
    """The big blue "booked" banner isn't in the generic top-of-page message
    list (Django orders message.tags as "<extra_tags> <level>", so building
    the CSS class from that combined string silently produced a class no
    selector matched) - it renders once, between the booking details and the
    reschedule calendar."""
    resp = client.post("/schedule/book/", _details(start=slot.isoformat()))
    body = client.get(resp.url).content.decode()

    assert body.count("Your meeting is booked!") == 1
    assert 'class="msg msg--success booked"' in body
    assert body.index("</dl>") < body.index("Your meeting is booked!") < body.index("Reschedule")


def test_htmx_booking_redirects_via_header(client, slot):
    resp = client.post(
        "/schedule/book/", _details(start=slot.isoformat()), headers={"HX-Request": "true"}
    )
    assert resp.status_code == 204
    assert resp["HX-Redirect"].startswith("/b/")


def test_double_booking_via_page_is_blocked(client, slot):
    assert client.post("/schedule/book/", _details(start=slot.isoformat())).status_code == 302

    resp = client.post(
        "/schedule/book/", _details(start=slot.isoformat(), client_email="second@example.com")
    )
    assert resp.status_code == 200  # re-rendered with an error
    assert Booking.objects.count() == 1


def test_japan_and_headhunting_are_separate_exclusivity_tracks(client, slot):
    """Japan bookings go to a different person than Headhunting/Global, so
    the same time slot can be booked once per track."""
    first = client.post("/schedule/book/", _details(start=slot.isoformat(), service="headhunting"))
    assert first.status_code == 302

    second = client.post(
        "/schedule/book/",
        _details(start=slot.isoformat(), service="japan", client_email="second@example.com"),
    )
    assert second.status_code == 302
    assert Booking.objects.filter(start_at=slot, status=Booking.Status.CONFIRMED).count() == 2


def test_available_slots_are_scoped_per_exclusivity_track(client, slot):
    """The same function that feeds both the slot grid and the month
    calendar's day-shading respects the track split."""
    client.post("/schedule/book/", _details(start=slot.isoformat(), service="headhunting"))

    rules = Rules.current()
    day = slot.date()
    assert slot not in available_slots(day, rules, service="headhunting")
    assert slot in available_slots(day, rules, service="japan")


def test_headhunting_and_global_share_one_exclusivity_track(client, slot):
    first = client.post("/schedule/book/", _details(start=slot.isoformat(), service="headhunting"))
    assert first.status_code == 302

    second = client.post(
        "/schedule/book/",
        _details(start=slot.isoformat(), service="global", client_email="second@example.com"),
    )
    assert second.status_code == 200  # re-rendered with an error
    assert Booking.objects.filter(start_at=slot).count() == 1


def test_missing_details_re_renders_form(client, slot):
    resp = client.post("/schedule/book/", {"start": slot.isoformat(), "client_name": "Only Name"})
    assert resp.status_code == 200
    assert Booking.objects.count() == 0


def test_reschedule_flow(client, slot, other_slot):
    client.post("/schedule/book/", _details(start=slot.isoformat()))
    booking = Booking.objects.get()

    resp = client.post(f"/b/{booking.manage_token}/reschedule/", {"start": other_slot.isoformat()})
    assert resp.status_code == 302
    booking.refresh_from_db()
    assert booking.start_at == other_slot


def test_confirm_new_time_button_disables_itself_on_click(client, slot, other_slot):
    """Same double-submit race as the booking button - see the test above."""
    client.post("/schedule/book/", _details(start=slot.isoformat()))
    booking = Booking.objects.get()

    body = client.get(
        f"/b/{booking.manage_token}/", {"start": other_slot.isoformat()}
    ).content.decode()
    assert 'hx-disabled-elt="this"' in body


def test_cancel_flow(client, slot):
    client.post("/schedule/book/", _details(start=slot.isoformat()))
    booking = Booking.objects.get()

    resp = client.post(f"/b/{booking.manage_token}/cancel/")
    assert resp.status_code == 302
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_only_30_minute_meetings_by_default(client, slot):
    """MAX_CONSECUTIVE_SLOTS defaults to 1 - no length choice, no hour booking."""
    resp = client.get("/schedule/", {"date": slot.date().isoformat(), "start": slot.isoformat()})
    body = resp.content.decode()
    assert "Meeting length" not in body
    assert 'name="slot_count" value="1"' in body

    client.post("/schedule/book/", _details(start=slot.isoformat(), slot_count="2"))
    assert Booking.objects.get().slot_count == 1


def test_longer_meetings_when_the_cap_is_raised(client, slot, long_meetings):
    resp = client.get("/schedule/", {"date": slot.date().isoformat(), "start": slot.isoformat()})
    assert "1 hour" in resp.content.decode()

    client.post("/schedule/book/", _details(start=slot.isoformat(), slot_count="2"))
    booking = Booking.objects.get()
    assert booking.slot_count == 2
    assert booking.duration_minutes == 60


def test_hour_booking_blocks_both_slots(client, slot, next_slot, long_meetings):
    client.post("/schedule/book/", _details(start=slot.isoformat(), slot_count="2"))

    open_slots = client.get("/api/slots/", {"day": slot.date().isoformat()}).json()["slots"]
    assert slot.isoformat() not in open_slots
    assert next_slot.isoformat() not in open_slots


def test_slot_count_above_max_is_clamped(client, slot, long_meetings):
    client.post("/schedule/book/", _details(start=slot.isoformat(), slot_count="5"))
    assert Booking.objects.get().slot_count == 2


def test_reschedule_keeps_the_duration(client, slot, other_slot, long_meetings):
    client.post("/schedule/book/", _details(start=slot.isoformat(), slot_count="2"))
    booking = Booking.objects.get()

    resp = client.post(f"/b/{booking.manage_token}/reschedule/", {"start": other_slot.isoformat()})
    assert resp.status_code == 302
    booking.refresh_from_db()
    assert booking.start_at == other_slot
    assert booking.slot_count == 2
    assert booking.duration_minutes == 60


def test_booked_service_is_saved_and_shown_on_the_manage_page(client, slot):
    resp = client.post("/schedule/book/", _details(start=slot.isoformat(), service="headhunting"))
    booking = Booking.objects.get()
    assert booking.service == "headhunting"

    manage = client.get(resp.url)
    assert "Headhunting" in manage.content.decode()


def test_an_invalid_service_is_not_saved(client, slot):
    client.post("/schedule/book/", _details(start=slot.isoformat(), service="bogus"))
    assert Booking.objects.get().service == ""


def test_unknown_token_is_404(client):
    assert client.get("/b/nope/").status_code == 404


def test_admin_requires_login(client):
    resp = client.get("/admin/")
    assert resp.status_code == 302
    assert "/login" in resp.url
