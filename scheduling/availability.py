"""Slot generation and availability checks.

All datetimes here are timezone-aware UTC (Django's convention with USE_TZ=True).
Business hours from `Rules` are interpreted in `rules.timezone`.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import Booking
from .rules import Rules

UTC = ZoneInfo("UTC")


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


def _confirmed_starts(day_slots: list[datetime]) -> set[datetime]:
    if not day_slots:
        return set()
    return set(
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            start_at__gte=min(day_slots),
            start_at__lte=max(day_slots),
        ).values_list("start_at", flat=True)
    )


def available_slots(
    day: date, rules: Rules, *, ignore_start: datetime | None = None
) -> list[datetime]:
    """Bookable slot starts on `day` (aware UTC), soonest first.

    `ignore_start` lets a reschedule treat its own current slot as free.
    """
    now = timezone.now()
    earliest = now + timedelta(hours=rules.min_notice_hours)
    latest = now + timedelta(days=rules.booking_horizon_days)

    slots = generate_day_slots(day, rules)
    taken = _confirmed_starts(slots)
    if ignore_start is not None:
        taken.discard(ignore_start)

    return [s for s in slots if earliest <= s <= latest and s not in taken]


def is_slot_available(
    start_at: datetime, rules: Rules, *, ignore_start: datetime | None = None
) -> bool:
    day = local_date_of(start_at, rules)
    return start_at in available_slots(day, rules, ignore_start=ignore_start)


def days_with_availability(days: list[date], rules: Rules) -> dict[date, bool]:
    """For each date, whether it has at least one bookable slot.

    Answers the whole list with a single bookings query - used to shade the
    month calendar without an N+1.
    """
    now = timezone.now()
    earliest = now + timedelta(hours=rules.min_notice_hours)
    latest = now + timedelta(days=rules.booking_horizon_days)

    per_day = {d: generate_day_slots(d, rules) for d in days}
    all_slots = [s for slots in per_day.values() for s in slots]
    if all_slots:
        taken = set(
            Booking.objects.filter(
                status=Booking.Status.CONFIRMED,
                start_at__gte=min(all_slots),
                start_at__lte=max(all_slots),
            ).values_list("start_at", flat=True)
        )
    else:
        taken = set()

    return {
        d: any(earliest <= s <= latest and s not in taken for s in slots)
        for d, slots in per_day.items()
    }
