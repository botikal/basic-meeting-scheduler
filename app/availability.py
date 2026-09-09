"""Slot generation and availability checks.

Business hours in `Settings` are expressed in `settings.timezone`. This module
turns them into concrete slot start times as *naive UTC* datetimes, then removes
slots that are already booked or outside the allowed booking window.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from .config import Settings
from .models import Booking, BookingStatus
from .timeutils import now_utc

UTC = ZoneInfo("UTC")


def slot_length(settings: Settings) -> timedelta:
    return timedelta(minutes=settings.slot_minutes)


def local_date_of(start_at: datetime, settings: Settings) -> date:
    """The calendar date a naive-UTC slot falls on in the business timezone."""
    return start_at.replace(tzinfo=UTC).astimezone(ZoneInfo(settings.timezone)).date()


def generate_day_slots(day: date, settings: Settings) -> list[datetime]:
    """All slot start times on `day` per the business-hours rules (naive UTC).

    Ignores existing bookings and the notice/horizon window - that filtering
    happens in `available_slots`.
    """
    if day.weekday() not in settings.available_weekdays:
        return []

    tz = ZoneInfo(settings.timezone)
    step = slot_length(settings)
    start_local = datetime.combine(day, time(hour=settings.business_start_hour), tzinfo=tz)
    end_local = datetime.combine(day, time(hour=settings.business_end_hour), tzinfo=tz)

    slots: list[datetime] = []
    cursor = start_local
    while cursor + step <= end_local:
        slots.append(cursor.astimezone(UTC).replace(tzinfo=None))
        cursor += step
    return slots


def _booked_starts(session: Session, day_slots: list[datetime]) -> set[datetime]:
    if not day_slots:
        return set()
    rows = session.exec(
        select(Booking.start_at).where(
            Booking.status == BookingStatus.confirmed,
            Booking.start_at >= min(day_slots),
            Booking.start_at <= max(day_slots),
        )
    ).all()
    return set(rows)


def available_slots(
    session: Session, day: date, settings: Settings, *, ignore_start: datetime | None = None
) -> list[datetime]:
    """Bookable slot start times on `day` (naive UTC), soonest first.

    `ignore_start` lets a reschedule treat its own current slot as free.
    """
    now = now_utc()
    earliest = now + timedelta(hours=settings.min_notice_hours)
    latest = now + timedelta(days=settings.booking_horizon_days)

    slots = generate_day_slots(day, settings)
    taken = _booked_starts(session, slots)
    if ignore_start is not None:
        taken.discard(ignore_start)

    return [s for s in slots if earliest <= s <= latest and s not in taken]


def is_slot_available(
    session: Session,
    start_at: datetime,
    settings: Settings,
    *,
    ignore_start: datetime | None = None,
) -> bool:
    day = local_date_of(start_at, settings)
    return start_at in available_slots(session, day, settings, ignore_start=ignore_start)
