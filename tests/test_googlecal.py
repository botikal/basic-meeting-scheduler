"""Tests for the Google Calendar / Meet integration.

Google Calendar is force-disabled in every test (see conftest._no_google_calendar),
so these mock `scheduling.googlecal` directly rather than hitting the network.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from scheduling import googlecal
from scheduling.models import Booking
from scheduling.services import (
    SlotUnavailable,
    cancel_booking,
    create_booking,
    reschedule_booking,
)

pytestmark = pytest.mark.django_db


def _booking(slot, **overrides):
    data = {
        "client_name": "Dana Client",
        "client_email": "dana@example.com",
        "start_at": slot,
    }
    data.update(overrides)
    return create_booking(**data)


def test_booking_has_no_meet_link_when_google_calendar_is_off(client, slot):
    booking = _booking(slot)
    assert booking.calendar_event_id == ""
    assert booking.meet_url == ""


def test_booking_gets_a_meet_link_when_configured(slot):
    with patch(
        "scheduling.googlecal.create_event",
        return_value=("evt123", "https://meet.google.com/abc-defg-hij"),
    ) as mock_create:
        booking = _booking(slot)

    mock_create.assert_called_once_with(booking)
    booking.refresh_from_db()
    assert booking.calendar_event_id == "evt123"
    assert booking.meet_url == "https://meet.google.com/abc-defg-hij"


def test_a_failed_calendar_call_does_not_block_the_booking(slot):
    with patch("scheduling.googlecal.create_event", return_value=None):
        booking = _booking(slot)
    assert booking.status == Booking.Status.CONFIRMED
    assert booking.meet_url == ""


def test_reschedule_updates_the_calendar_event(slot, other_slot):
    booking = _booking(slot)
    with patch("scheduling.googlecal.update_event") as mock_update:
        reschedule_booking(booking, other_slot)
    mock_update.assert_called_once_with(booking)


def test_cancel_deletes_the_calendar_event(slot):
    booking = _booking(slot)
    with patch("scheduling.googlecal.delete_event") as mock_delete:
        cancel_booking(booking)
    mock_delete.assert_called_once_with(booking)


# --- googlecal internals: what actually gets sent to the Google API --------


def _unsaved_booking(slot, **overrides):
    booking = Booking(
        pk=1,
        client_name="Dana Client",
        client_email="dana@example.com",
        note="Kickoff call",
        start_at=slot,
        end_at=slot + timedelta(minutes=30),
    )
    for key, value in overrides.items():
        setattr(booking, key, value)
    return booking


def test_create_event_invites_the_client_and_emails_the_invite(slot, settings):
    settings.GOOGLE_CALENDAR = {"TOKEN_FILE": "unused.json", "CALENDAR_ID": "cal@example.com"}
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt1",
        "hangoutLink": "https://meet.google.com/xyz-abcd-efg",
    }

    with patch("scheduling.googlecal._service", return_value=fake_service):
        result = googlecal.create_event(_unsaved_booking(slot))

    assert result == ("evt1", "https://meet.google.com/xyz-abcd-efg")
    _, kwargs = fake_service.events.return_value.insert.call_args
    assert kwargs["sendUpdates"] == "all"
    assert kwargs["body"]["attendees"] == [
        {"email": "dana@example.com", "displayName": "Dana Client"}
    ]
    assert kwargs["body"]["summary"] == "Meeting with Dana Client"


def test_create_event_adds_the_configured_notify_email_as_an_extra_attendee(slot, settings):
    """Piggybacks on Google's own invite/update/cancellation emails (already
    working) instead of needing a separate SMTP setup - update_event/
    delete_event don't need their own copy of this: Google Calendar keeps an
    event's attendee list across patches and deletes, so setting it once
    here at creation is enough for all three."""
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "CALENDAR_ID": "cal@example.com",
        "NOTIFY_EMAIL": "global@wantedlab.com",
    }
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt1"}

    with patch("scheduling.googlecal._service", return_value=fake_service):
        googlecal.create_event(_unsaved_booking(slot))

    _, kwargs = fake_service.events.return_value.insert.call_args
    assert kwargs["body"]["attendees"] == [
        {"email": "dana@example.com", "displayName": "Dana Client"},
        {"email": "global@wantedlab.com"},
    ]


def test_event_title_names_the_service_when_one_was_picked(slot, settings):
    settings.GOOGLE_CALENDAR = {"TOKEN_FILE": "unused.json", "CALENDAR_ID": "cal@example.com"}
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt1"}

    with patch("scheduling.googlecal._service", return_value=fake_service):
        googlecal.create_event(_unsaved_booking(slot, service="headhunting"))

    _, kwargs = fake_service.events.return_value.insert.call_args
    assert kwargs["body"]["summary"] == "Meeting for Headhunting with Dana Client"


def test_event_title_shortens_the_global_service_label(slot, settings):
    """Booking.Service's GLOBAL label ("Wanted Global service introduction")
    is written for the landing page, not a calendar title."""
    settings.GOOGLE_CALENDAR = {"TOKEN_FILE": "unused.json", "CALENDAR_ID": "cal@example.com"}
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt1"}

    with patch("scheduling.googlecal._service", return_value=fake_service):
        googlecal.create_event(_unsaved_booking(slot, service="global"))

    _, kwargs = fake_service.events.return_value.insert.call_args
    assert kwargs["body"]["summary"] == "Meeting for Global services with Dana Client"


def test_update_event_notifies_the_attendee(slot, other_slot, settings):
    settings.GOOGLE_CALENDAR = {"TOKEN_FILE": "unused.json", "CALENDAR_ID": "cal@example.com"}
    new_end = other_slot + timedelta(minutes=30)
    booking = _unsaved_booking(slot, calendar_event_id="evt1", start_at=other_slot, end_at=new_end)
    fake_service = MagicMock()

    with patch("scheduling.googlecal._service", return_value=fake_service):
        googlecal.update_event(booking)

    _, kwargs = fake_service.events.return_value.patch.call_args
    assert kwargs["sendUpdates"] == "all"


def test_delete_event_notifies_the_attendee(slot, settings):
    settings.GOOGLE_CALENDAR = {"TOKEN_FILE": "unused.json", "CALENDAR_ID": "cal@example.com"}
    booking = _unsaved_booking(slot, calendar_event_id="evt1")
    fake_service = MagicMock()

    with patch("scheduling.googlecal._service", return_value=fake_service):
        googlecal.delete_event(booking)

    _, kwargs = fake_service.events.return_value.delete.call_args
    assert kwargs["sendUpdates"] == "all"


# --- Reading and writing different calendars per service -------------------


def test_write_calendar_defaults_to_the_main_read_calendar(settings):
    settings.GOOGLE_CALENDAR = {"TOKEN_FILE": "unused.json", "CALENDAR_ID": "cal@example.com"}
    assert googlecal.write_calendar_for("") == "cal@example.com"
    assert googlecal.write_calendar_for("headhunting") == "cal@example.com"
    assert googlecal.write_calendar_for("japan") == "cal@example.com"


def test_write_calendar_id_overrides_the_main_calendar(settings):
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "CALENDAR_ID": "cal@example.com",
        "WRITE_CALENDAR_ID": "bookings@example.com",
    }
    assert googlecal.write_calendar_for("") == "bookings@example.com"
    assert googlecal.write_calendar_for("headhunting") == "bookings@example.com"
    # No Japan-specific write calendar set, so Japan falls back to the same one.
    assert googlecal.write_calendar_for("japan") == "bookings@example.com"


def test_japan_write_calendar_id_only_applies_to_japan(settings):
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "CALENDAR_ID": "cal@example.com",
        "WRITE_CALENDAR_ID": "bookings@example.com",
        "JAPAN_WRITE_CALENDAR_ID": "japan-bookings@example.com",
    }
    assert googlecal.write_calendar_for("japan") == "japan-bookings@example.com"
    assert googlecal.write_calendar_for("headhunting") == "bookings@example.com"
    assert googlecal.write_calendar_for("") == "bookings@example.com"


def test_create_event_writes_to_the_service_specific_calendar(slot, settings):
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "CALENDAR_ID": "cal@example.com",
        "JAPAN_WRITE_CALENDAR_ID": "japan-bookings@example.com",
    }
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt1"}

    with patch("scheduling.googlecal._service", return_value=fake_service):
        googlecal.create_event(_unsaved_booking(slot, service="japan"))

    kwargs = fake_service.events.return_value.insert.call_args.kwargs
    assert kwargs["calendarId"] == "japan-bookings@example.com"


def test_update_and_delete_target_the_calendar_the_event_was_created_on(slot, settings):
    """Reschedule/cancel must hit the same calendar create_event wrote to -
    not the main read calendar - or the event id won't be found there."""
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "CALENDAR_ID": "cal@example.com",
        "JAPAN_WRITE_CALENDAR_ID": "japan-bookings@example.com",
    }
    booking = _unsaved_booking(slot, calendar_event_id="evt1", service="japan")
    fake_service = MagicMock()

    with patch("scheduling.googlecal._service", return_value=fake_service):
        googlecal.update_event(booking)
        googlecal.delete_event(booking)

    patch_kwargs = fake_service.events.return_value.patch.call_args.kwargs
    delete_kwargs = fake_service.events.return_value.delete.call_args.kwargs
    assert patch_kwargs["calendarId"] == "japan-bookings@example.com"
    assert delete_kwargs["calendarId"] == "japan-bookings@example.com"


# --- The extra Japan-calendar availability check ---------------------------


def test_extra_calendar_for_japan_reads_the_configured_calendar_id(settings):
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "CALENDAR_ID": "cal@example.com",
        "JAPAN_CALENDAR_ID": "japan@example.com",
    }
    assert googlecal.extra_calendar_for("japan") == "japan@example.com"


def test_extra_calendar_for_other_services_is_blank(settings):
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "CALENDAR_ID": "cal@example.com",
        "JAPAN_CALENDAR_ID": "japan@example.com",
    }
    assert googlecal.extra_calendar_for("headhunting") == ""
    assert googlecal.extra_calendar_for("") == ""


def test_extra_calendar_for_japan_is_blank_when_unconfigured(settings):
    settings.GOOGLE_CALENDAR = {"TOKEN_FILE": "unused.json", "CALENDAR_ID": "cal@example.com"}
    assert googlecal.extra_calendar_for("japan") == ""


def test_busy_intervals_returns_none_without_a_calendar_id():
    assert googlecal.busy_intervals("", timezone.now(), timezone.now()) is None


def test_busy_intervals_returns_none_when_google_calendar_is_off():
    # _no_google_calendar leaves TOKEN_FILE/CALENDAR_ID blank, so _service() is None.
    assert googlecal.busy_intervals("japan@example.com", timezone.now(), timezone.now()) is None


def test_busy_intervals_parses_the_freebusy_response(slot):
    fake_service = MagicMock()
    fake_service.freebusy.return_value.query.return_value.execute.return_value = {
        "calendars": {
            "japan@example.com": {
                "busy": [
                    {
                        "start": slot.isoformat(),
                        "end": (slot + timedelta(minutes=30)).isoformat(),
                    }
                ]
            }
        }
    }
    with patch("scheduling.googlecal._service", return_value=fake_service):
        result = googlecal.busy_intervals("japan@example.com", slot, slot + timedelta(hours=1))
    assert result == [(slot, slot + timedelta(minutes=30))]


def test_busy_intervals_returns_none_when_the_api_call_fails():
    fake_service = MagicMock()
    fake_service.freebusy.return_value.query.return_value.execute.side_effect = Exception("boom")
    with patch("scheduling.googlecal._service", return_value=fake_service):
        assert googlecal.busy_intervals("japan@example.com", timezone.now(), timezone.now()) is None


def test_busy_intervals_returns_none_when_service_construction_fails():
    """_service() itself can raise - e.g. GOOGLE_TOKEN_FILE/CALENDAR_ID are
    set but the token file doesn't actually exist on disk yet (GOOGLE_TOKEN_JSON
    never got materialized). That used to crash the whole request with a 500
    instead of the "unknown, don't filter on it" None every other failure
    mode here returns - this is the calendar-date-click bug fix."""
    with patch("scheduling.googlecal._service", side_effect=FileNotFoundError("no token.json")):
        assert googlecal.busy_intervals("japan@example.com", timezone.now(), timezone.now()) is None


def test_japan_slot_busy_on_the_external_calendar_is_not_offered(client, slot, settings):
    # CALENDAR_ID left blank so only the Japan-specific calendar is in play.
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "JAPAN_CALENDAR_ID": "japan@example.com",
    }
    with patch(
        "scheduling.googlecal.busy_intervals",
        return_value=[(slot, slot + timedelta(minutes=30))],
    ):
        resp = client.get("/schedule/", {"service": "japan", "date": slot.date().isoformat()})
    assert slot.strftime("%H:%M") not in resp.content.decode()


def test_japan_booking_on_an_externally_busy_slot_is_rejected(slot, settings):
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "JAPAN_CALENDAR_ID": "japan@example.com",
    }
    with (
        patch(
            "scheduling.googlecal.busy_intervals",
            return_value=[(slot, slot + timedelta(minutes=30))],
        ),
        pytest.raises(SlotUnavailable),
    ):
        _booking(slot, service="japan")
    assert Booking.objects.count() == 0


# --- The main calendar's own events also block availability, for every
# service - not just Japan's extra check. -----------------------------------


def test_main_calendar_busy_time_blocks_any_booking(slot, settings):
    settings.GOOGLE_CALENDAR = {"TOKEN_FILE": "unused.json", "CALENDAR_ID": "cal@example.com"}
    with (
        patch(
            "scheduling.googlecal.busy_intervals",
            return_value=[(slot, slot + timedelta(minutes=30))],
        ),
        pytest.raises(SlotUnavailable),
    ):
        _booking(slot)  # no service picked - still checked
    assert Booking.objects.count() == 0


def test_japan_calendar_only_blocks_japan_bookings(slot, other_slot, settings):
    """A busy Japan calendar doesn't affect other services, and a free main
    calendar doesn't shield a Japan booking from a busy Japan calendar."""
    settings.GOOGLE_CALENDAR = {
        "TOKEN_FILE": "unused.json",
        "CALENDAR_ID": "cal@example.com",
        "JAPAN_CALENDAR_ID": "japan@example.com",
    }

    def fake_busy(calendar_id, start, end):
        if calendar_id != "japan@example.com":
            return []
        return [
            (slot, slot + timedelta(minutes=30)),
            (other_slot, other_slot + timedelta(minutes=30)),
        ]

    with patch("scheduling.googlecal.busy_intervals", side_effect=fake_busy):
        headhunting = _booking(slot, service="headhunting")
        assert headhunting.service == "headhunting"
        with pytest.raises(SlotUnavailable):
            _booking(other_slot, service="japan")
    assert Booking.objects.count() == 1
