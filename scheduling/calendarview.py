"""Helpers for rendering the month picker."""

import calendar
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from .availability import days_with_availability
from .models import Booking
from .rules import Rules

_CAL = calendar.Calendar(firstweekday=0)  # Monday first
WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class Day:
    date: date
    in_month: bool
    is_today: bool
    is_available: bool
    is_past: bool


@dataclass(frozen=True)
class MonthView:
    year: int
    month: int
    ym: str  # "YYYY-MM"
    label: str  # e.g. "September 2026"
    weeks: list[list[Day]]
    prev_month: str  # "YYYY-MM"
    next_month: str
    selected: date | None


def _shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def build_month(year: int, month: int, rules: Rules, selected: date | None = None) -> MonthView:
    today = timezone.localdate()
    grid = _CAL.monthdatescalendar(year, month)
    flat = [d for week in grid for d in week]
    availability = days_with_availability(flat, rules)

    weeks = [
        [
            Day(
                date=d,
                in_month=(d.month == month),
                is_today=(d == today),
                is_available=availability.get(d, False),
                is_past=(d < today),
            )
            for d in week
        ]
        for week in grid
    ]

    py, pm = _shift(year, month, -1)
    ny, nm = _shift(year, month, +1)
    return MonthView(
        year=year,
        month=month,
        ym=f"{year:04d}-{month:02d}",
        label=date(year, month, 1).strftime("%B %Y"),
        weeks=weeks,
        prev_month=f"{py:04d}-{pm:02d}",
        next_month=f"{ny:04d}-{nm:02d}",
        selected=selected,
    )


@dataclass(frozen=True)
class CountedDay:
    date: date
    in_month: bool
    is_today: bool
    is_selected: bool
    count: int  # confirmed bookings starting that day


def build_staff_month(
    year: int, month: int, rules: Rules, selected: date | None = None
) -> MonthView:
    """Month grid annotated with how many confirmed bookings fall on each day."""
    today = timezone.localdate()
    grid = _CAL.monthdatescalendar(year, month)
    tz = rules.tz

    span_start = datetime.combine(grid[0][0], time.min, tzinfo=tz)
    span_end = datetime.combine(grid[-1][-1] + timedelta(days=1), time.min, tzinfo=tz)
    starts = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_at__gte=span_start,
        start_at__lt=span_end,
    ).values_list("start_at", flat=True)
    counts = Counter(s.astimezone(tz).date() for s in starts)

    weeks = [
        [
            CountedDay(
                date=d,
                in_month=(d.month == month),
                is_today=(d == today),
                is_selected=(d == selected),
                count=counts.get(d, 0),
            )
            for d in week
        ]
        for week in grid
    ]

    py, pm = _shift(year, month, -1)
    ny, nm = _shift(year, month, +1)
    return MonthView(
        year=year,
        month=month,
        ym=f"{year:04d}-{month:02d}",
        label=date(year, month, 1).strftime("%B %Y"),
        weeks=weeks,
        prev_month=f"{py:04d}-{pm:02d}",
        next_month=f"{ny:04d}-{nm:02d}",
        selected=selected,
    )


def parse_month(raw: str | None) -> tuple[int, int]:
    """Parse 'YYYY-MM'; fall back to the current month."""
    today = timezone.localdate()
    if raw:
        try:
            year, month = (int(part) for part in raw.split("-", 1))
            if 1 <= month <= 12 and 1900 <= year <= 2100:
                return year, month
        except ValueError, TypeError:
            pass
    return today.year, today.month
