"""Booking operations shared by the page views and the JSON API."""

from datetime import datetime

from django.db import IntegrityError, transaction

from .availability import can_book
from .emails import send_cancellation, send_confirmation
from .models import Booking
from .rules import Rules


class SlotUnavailable(Exception):
    """Raised when a requested slot cannot be booked."""


def _clamp_slots(raw, rules: Rules) -> int:
    try:
        value = int(raw)
    except TypeError, ValueError:
        value = 1
    return max(1, min(value, rules.max_consecutive_slots))


def _unavailable_message(slot_count: int, rules: Rules) -> str:
    if slot_count <= 1:
        return "That time is not available."
    return f"There isn't a free {slot_count * rules.slot_minutes}-minute block starting then."


def create_booking(
    *,
    client_name: str,
    client_email: str,
    start_at: datetime,
    note: str = "",
    slot_count: int = 1,
    rules: Rules | None = None,
) -> Booking:
    rules = rules or Rules.current()
    slot_count = _clamp_slots(slot_count, rules)
    try:
        # The availability check and the insert run in one transaction so a
        # concurrent booking can't slip into the same slots between them.
        with transaction.atomic():
            if not can_book(start_at, rules, slot_count):
                raise SlotUnavailable(_unavailable_message(slot_count, rules))
            booking = Booking.objects.create(
                client_name=client_name.strip(),
                client_email=client_email,
                start_at=start_at,
                end_at=start_at + slot_count * rules.slot_length,
                slot_count=slot_count,
                note=(note or "").strip(),
            )
    except IntegrityError as exc:  # lost a race for the starting slot
        raise SlotUnavailable("That time was just taken.") from exc
    send_confirmation(booking)
    return booking


def reschedule_booking(
    booking: Booking,
    new_start: datetime,
    rules: Rules | None = None,
    slot_count: int | None = None,
) -> Booking:
    rules = rules or Rules.current()
    if not booking.is_confirmed:
        raise SlotUnavailable("Only confirmed bookings can be rescheduled.")

    target = _clamp_slots(slot_count if slot_count is not None else booking.slot_count, rules)
    try:
        with transaction.atomic():
            if not can_book(new_start, rules, target, exclude_id=booking.pk):
                raise SlotUnavailable(_unavailable_message(target, rules))
            booking.start_at = new_start
            booking.end_at = new_start + target * rules.slot_length
            booking.slot_count = target
            booking.save(update_fields=["start_at", "end_at", "slot_count"])
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
