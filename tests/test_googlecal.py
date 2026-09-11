"""Tests for the Google Calendar / Meet integration.

Google Calendar is force-disabled in every test (see conftest._no_google_calendar),
so these mock `scheduling.googlecal` directly rather than hitting the network.
"""

from unittest.mock import patch

import pytest

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
