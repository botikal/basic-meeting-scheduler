"""A failed *or slow* send must never block the booking it's about, or the
response the client is waiting on - see googlecal.py for the same pattern
with Google Calendar."""

import threading
import time
from contextlib import contextmanager
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


@contextmanager
def _run_background_sends_synchronously():
    """emails._send_async fires on a real background thread (the whole
    point - see the module docstring), which makes it non-deterministic to
    test directly: a mock's `with patch(...)` block can exit, restoring the
    real send_mail, before the OS ever schedules that thread to run it. Runs
    the target inline instead, so tests can reliably assert on what actually
    happened inside it."""
    with patch.object(threading.Thread, "start", lambda self: self.run()):
        yield


def test_a_broken_smtp_config_does_not_block_booking(slot):
    with _run_background_sends_synchronously():
        with patch("scheduling.emails.send_mail", side_effect=Exception("smtp rejected")):
            booking = _booking(slot)
    assert booking.status == Booking.Status.CONFIRMED


def test_a_broken_smtp_config_does_not_block_cancellation(slot):
    booking = _booking(slot)
    with _run_background_sends_synchronously():
        with patch("scheduling.emails.send_mail", side_effect=Exception("smtp rejected")):
            cancel_booking(booking)
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_a_slow_mail_server_does_not_delay_the_booking_response(slot):
    """The actual bug this was written for: a booking that took 22s on a
    real deployment because the mail send blocked the response, even though
    it eventually succeeded - long enough that clients gave up before ever
    seeing their own successful booking confirmed."""

    def _slow_send(**kwargs):
        time.sleep(0.3)

    with patch("scheduling.emails.send_mail", side_effect=_slow_send):
        started = time.monotonic()
        _booking(slot)
        elapsed = time.monotonic() - started

    assert elapsed < 0.2, f"create_booking waited on the mail send ({elapsed:.2f}s)"
