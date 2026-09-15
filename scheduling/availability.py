"""Slot generation and availability checks.

All datetimes here are timezone-aware UTC (Django's convention with USE_TZ=True).
Business hours are expressed in ``rules.business_timezone``; a "day" that a client
picks is a date in ``rules.display_timezone``, so slot generation walks the
business grid and keeps the slots whose *display* date matches.

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

# Japan bookings go to a different person than Headhunting/Global, so the two
# don't need to block each other - each is its own exclusivity track. Kept as
# a plain string (matching Booking.Service.JAPAN's value) rather than a new
# field, consistent with googlecal.write_calendar_for/extra_calendar_for.
TRACK_JAPAN = "japan"


def _in_japan_track(service: str) -> bool:
    return service == TRACK_JAPAN


def generate_day_slots(day: date, rules: Rules) -> list[datetime]:
    """Slot starts whose *display date* is `day` (aware UTC), business hours
    only, minus the lunch break.

    Ignores existing bookings and the notice/horizon window.
    """
    step = rules.slot_length
    business_tz = rules.business_tz
    display_tz = rules.display_tz
    found: set[datetime] = set()

    # A display day can draw slots from up to two adjacent business days.
    for offset in (-1, 0, 1):
        business_day = day + timedelta(days=offset)
        if business_day.weekday() not in rules.available_weekdays:
            continue
        cursor = datetime.combine(
            business_day, time(hour=rules.business_start_hour), tzinfo=business_tz
        )
        end_local = datetime.combine(
            business_day, time(hour=rules.business_end_hour), tzinfo=business_tz
        )
        lunch_start = datetime.combine(
            business_day, time(hour=rules.lunch_start_hour), tzinfo=business_tz
        )
        lunch_end = datetime.combine(
            business_day, time(hour=rules.lunch_end_hour), tzinfo=business_tz
        )
        while cursor + step <= end_local:
            if cursor < lunch_end and cursor + step > lunch_start:
                cursor += step
                continue
            moment = cursor.astimezone(UTC)
            if moment.astimezone(display_tz).date() == day:
                found.add(moment)
            cursor += step

    return sorted(found)


def local_date_of(moment: datetime, rules: Rules) -> date:
    """The calendar date `moment` falls on in the client-facing timezone."""
    return moment.astimezone(rules.display_tz).date()


def _confirmed_intervals(
    window_start: datetime,
    window_end: datetime,
    *,
    service: str = "",
    exclude_id: int | None = None,
) -> list[Interval]:
    """(start, end) of every confirmed booking *in the same exclusivity
    track as `service`* that overlaps the window - see TRACK_JAPAN."""
    query = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_at__lt=window_end,
        end_at__gt=window_start,
    )
    if _in_japan_track(service):
        query = query.filter(service=TRACK_JAPAN)
    else:
        query = query.exclude(service=TRACK_JAPAN)
    if exclude_id is not None:
        query = query.exclude(pk=exclude_id)
    return list(query.values_list("start_at", "end_at"))


def _overlaps(start: datetime, end: datetime, intervals: list[Interval]) -> bool:
    return any(start < iv_end and end > iv_start for iv_start, iv_end in intervals)


def available_slots(
    day: date,
    rules: Rules,
    *,
    service: str = "",
    exclude_id: int | None = None,
    extra_busy: list[Interval] | None = None,
) -> list[datetime]:
    """Single (30-minute) slot starts on `day` that are free to book, soonest first.

    `service` scopes which existing bookings count against this one - see
    TRACK_JAPAN. `exclude_id` frees the slots held by one booking - used when
    rescheduling it. `extra_busy` additionally excludes slots overlapping
    those intervals - used for services that also check an external calendar
    (see extra_busy_for).
    """
    slots = generate_day_slots(day, rules)
    if not slots:
        return []

    now = timezone.now()
    earliest = now + timedelta(hours=rules.min_notice_hours)
    latest = now + timedelta(days=rules.booking_horizon_days)
    step = rules.slot_length
    intervals = _confirmed_intervals(
        slots[0], slots[-1] + step, service=service, exclude_id=exclude_id
    )
    if extra_busy:
        intervals = [*intervals, *extra_busy]

    return [s for s in slots if earliest <= s <= latest and not _overlaps(s, s + step, intervals)]


def consecutive_capacity(
    start: datetime,
    rules: Rules,
    *,
    service: str = "",
    exclude_id: int | None = None,
    extra_busy: list[Interval] | None = None,
) -> int:
    """How many back-to-back slots can be booked from `start` (0..max).

    0 means `start` itself is not a bookable slot. `service` scopes which
    existing bookings count against this one - see TRACK_JAPAN.
    """
    day_starts = set(generate_day_slots(local_date_of(start, rules), rules))
    step = rules.slot_length
    now = timezone.now()
    earliest = now + timedelta(hours=rules.min_notice_hours)
    latest = now + timedelta(days=rules.booking_horizon_days)
    intervals = _confirmed_intervals(
        start,
        start + rules.max_consecutive_slots * step,
        service=service,
        exclude_id=exclude_id,
    )
    if extra_busy:
        intervals = [*intervals, *extra_busy]

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
    start: datetime,
    rules: Rules,
    slot_count: int,
    *,
    service: str = "",
    exclude_id: int | None = None,
    extra_busy: list[Interval] | None = None,
) -> bool:
    return (
        1 <= slot_count <= rules.max_consecutive_slots
        and consecutive_capacity(
            start, rules, service=service, exclude_id=exclude_id, extra_busy=extra_busy
        )
        >= slot_count
    )


def extra_busy_for(service: str, day: date, rules: Rules) -> list[Interval] | None:
    """Busy periods on external Google Calendars that should also block
    availability on `day`, beyond our own confirmed bookings.

    Always includes the main calendar bookings are created on (see
    googlecal.main_calendar_id), plus - for a service with one configured,
    currently just "japan" - a service-specific calendar (see
    googlecal.extra_calendar_for). None only if no calendar could be checked
    at all: nothing configured, or every lookup failed - see
    googlecal.busy_intervals.
    """
    from . import googlecal  # local import: keeps this module DB-only by default

    candidates = (googlecal.main_calendar_id(), googlecal.extra_calendar_for(service))
    calendar_ids = list(dict.fromkeys(cid for cid in candidates if cid))
    if not calendar_ids:
        return None
    slots = generate_day_slots(day, rules)
    if not slots:
        return None
    start, end = slots[0], slots[-1] + rules.slot_length

    busy: list[Interval] = []
    found_any = False
    for calendar_id in calendar_ids:
        result = googlecal.busy_intervals(calendar_id, start, end)
        if result is not None:
            found_any = True
            busy.extend(result)
    return busy if found_any else None


def days_with_availability(
    days: list[date], rules: Rules, *, service: str = ""
) -> dict[date, bool]:
    """For each date, whether it has at least one free slot in `service`'s
    exclusivity track (see TRACK_JAPAN).

    Answers the whole list with a single bookings query - used to shade the
    month calendar without an N+1.
    """
    now = timezone.now()
    earliest = now + timedelta(hours=rules.min_notice_hours)
    latest = now + timedelta(days=rules.booking_horizon_days)
    step = rules.slot_length

    per_day = {d: generate_day_slots(d, rules) for d in days}
    all_slots = [s for slots in per_day.values() for s in slots]
    intervals = (
        _confirmed_intervals(min(all_slots), max(all_slots) + step, service=service)
        if all_slots
        else []
    )

    return {
        d: any(earliest <= s <= latest and not _overlaps(s, s + step, intervals) for s in slots)
        for d, slots in per_day.items()
    }
