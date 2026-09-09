"""Booking operations shared by the page views and the JSON API."""

from datetime import datetime

from django.db import IntegrityError, transaction

from .availability import is_slot_available
from .emails import send_cancellation, send_confirmation
from .models import Booking
from .rules import Rules


class SlotUnavailable(Exception):
    """Raised when a requested slot cannot be booked."""


def create_booking(
    *,
    client_name: str,
    client_email: str,
    start_at: datetime,
    note: str = "",
    rules: Rules | None = None,
) -> Booking:
    rules = rules or Rules.current()
    if not is_slot_available(start_at, rules):
        raise SlotUnavailable("That time is not available.")
    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                client_name=client_name.strip(),
                client_email=client_email,
                start_at=start_at,
                end_at=start_at + rules.slot_length,
                note=(note or "").strip(),
            )
    except IntegrityError as exc:  # lost a race for the same slot
        raise SlotUnavailable("That time was just taken.") from exc
    send_confirmation(booking)
    return booking


def reschedule_booking(
    booking: Booking, new_start: datetime, rules: Rules | None = None
) -> Booking:
    rules = rules or Rules.current()
    if not booking.is_confirmed:
        raise SlotUnavailable("Only confirmed bookings can be rescheduled.")
    if not is_slot_available(new_start, rules, ignore_start=booking.start_at):
        raise SlotUnavailable("That time is not available.")
    booking.start_at = new_start
    booking.end_at = new_start + rules.slot_length
    try:
        with transaction.atomic():
            booking.save(update_fields=["start_at", "end_at"])
    except IntegrityError as exc:
        raise SlotUnavailable("That time was just taken.") from exc
    send_confirmation(booking)
    return booking


def cancel_booking(booking: Booking) -> Booking:
    if not booking.is_confirmed:
        return booking
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=["status"])
    send_cancellation(booking)
    return booking
