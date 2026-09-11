"""Tests for the Google Calendar / Meet integration.

Google Calendar is force-disabled in every test (see conftest._no_google_calendar),
so these mock `scheduling.googlecal` directly rather than hitting the network.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from scheduling import googlecal
from scheduling.models import Booking
from scheduling.services import cancel_booking, create_booking, reschedule_booking

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
