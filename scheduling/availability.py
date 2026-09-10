"""Slot generation and availability checks.

All datetimes here are timezone-aware UTC (Django's convention with USE_TZ=True).
Business hours from `Rules` are interpreted in `rules.timezone`.

A booking can occupy several back-to-back slots (up to
``rules.max_consecutive_slots``), so availability is checked by *interval
overlap* against existing confirmed bookings, not just by matching start times.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import Booking
from .rules import Rules

UTC = ZoneInfo("UTC")

Interval = tuple[datetime, datetime]


def generate_day_slots(day: date, rules: Rules) -> list[datetime]:
    """Every slot start on `day` per the business-hours rules (aware UTC).

    Ignores existing bookings and the notice/horizon window.
    """
    if day.weekday() not in rules.available_weekdays:
        return []

    step = rules.slot_length
    start_local = datetime.combine(day, time(hour=rules.business_start_hour), tzinfo=rules.tz)
    end_local = datetime.combine(day, time(hour=rules.business_end_hour), tzinfo=rules.tz)

    slots: list[datetime] = []
    cursor = start_local
    while cursor + step <= end_local:
        slots.append(cursor.astimezone(UTC))
        cursor += step
    return slots


def local_date_of(moment: datetime, rules: Rules) -> date:
    """The calendar date `moment` falls on in the business timezone."""
    return moment.astimezone(rules.tz).date()


def _confirmed_intervals(
    window_start: datetime, window_end: datetime, *, exclude_id: int | None = None
) -> list[Interval]:
    """(start, end) of every confirmed booking that overlaps the window."""
    query = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_at__lt=window_end,
        end_at__gt=window_start,
    )
    if exclude_id is not None:
        query = query.exclude(pk=exclude_id)
    return list(query.values_list("start_at", "end_at"))


def _overlaps(start: datetime, end: datetime, intervals: list[Interval]) -> bool:
    return any(start < iv_end and end > iv_start for iv_start, iv_end in intervals)


def available_slots(day: date, rules: Rules, *, exclude_id: int | None = None) -> list[datetime]:
    """Single (30-minute) slot starts on `day` that are free to book, soonest first.

    `exclude_id` frees the slots held by one booking - used when rescheduling it.
    """
    slots = generate_day_slots(day, rules)
    if not slots:
        return []

    now = timezone.now()
    earliest = now + timedelta(hours=rules.min_notice_hours)
    latest = now + timedelta(days=rules.booking_horizon_days)
    step = rules.slot_length
    intervals = _confirmed_intervals(slots[0], slots[-1] + step, exclude_id=exclude_id)

    return [s for s in slots if earliest <= s <= latest and not _overlaps(s, s + step, intervals)]


def consecutive_capacity(start: datetime, rules: Rules, *, exclude_id: int | None = None) -> int:
    """How many back-to-back slots can be booked from `start` (0..max).

    0 means `start` itself is not a bookable slot.
    """
    day_starts = set(generate_day_slots(local_date_of(start, rules), rules))
    step = rules.slot_length
    now = timezone.now()
    earliest = now + timedelta(hours=rules.min_notice_hours)
    latest = now + timedelta(days=rules.booking_horizon_days)
    intervals = _confirmed_intervals(
        start, start + rules.max_consecutive_slots * step, exclude_id=exclude_id
    )

    count = 0
    cursor = start
    for _ in range(rules.max_consecutive_slots):
        if cursor not in day_starts:
            break
        if not (earliest <= cursor <= latest):
            break
        if _overlaps(cursor, cursor + step, intervals):
            break
        count += 1
        cursor += step
    return count


def can_book(
    start: datetime, rules: Rules, slot_count: int, *, exclude_id: int | None = None
) -> bool:
    return (
        1 <= slot_count <= rules.max_consecutive_slots
        and consecutive_capacity(start, rules, exclude_id=exclude_id) >= slot_count
    )


def days_with_availability(days: list[date], rules: Rules) -> dict[date, bool]:
    """For each date, whether it has at least one free slot.

    Answers the whole list with a single bookings query - used to shade the
    month calendar without an N+1.
    """
    now = timezone.now()
    earliest = now + timedelta(hours=rules.min_notice_hours)
    latest = now + timedelta(days=rules.booking_horizon_days)
    step = rules.slot_length

    per_day = {d: generate_day_slots(d, rules) for d in days}
    all_slots = [s for slots in per_day.values() for s in slots]
    intervals = _confirmed_intervals(min(all_slots), max(all_slots) + step) if all_slots else []

    return {
        d: any(earliest <= s <= latest and not _overlaps(s, s + step, intervals) for s in slots)
        for d, slots in per_day.items()
    }
