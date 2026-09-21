"""A failed send must never block the booking it's about - see googlecal.py
for the same pattern with Google Calendar."""

from unittest.mock import patch

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


def test_a_broken_smtp_config_does_not_block_booking(slot):
    with patch("scheduling.emails.send_mail", side_effect=Exception("smtp rejected")):
        booking = _booking(slot)
    assert booking.status == Booking.Status.CONFIRMED


def test_a_broken_smtp_config_does_not_block_cancellation(slot):
    booking = _booking(slot)
    with patch("scheduling.emails.send_mail", side_effect=Exception("smtp rejected")):
        cancel_booking(booking)
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
