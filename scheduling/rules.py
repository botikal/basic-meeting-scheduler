"""Typed access to the booking rules configured in settings.SCHEDULER."""

from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings


@dataclass(frozen=True)
class Rules:
    host_name: str
    base_url: str
    # The business's own timezone: business hours are expressed in it, and the
    # staff pages display times in it.
    business_timezone: str
    # What clients see times in (e.g. "UTC").
    display_timezone: str
    business_start_hour: int
    business_end_hour: int
    slot_minutes: int
    max_consecutive_slots: int
    available_weekdays: tuple[int, ...]
    booking_horizon_days: int
    min_notice_hours: int

    @classmethod
    def current(cls) -> Rules:
        cfg = settings.SCHEDULER
        return cls(
            host_name=cfg["HOST_NAME"],
            base_url=cfg["BASE_URL"].rstrip("/"),
            business_timezone=cfg["BUSINESS_TIMEZONE"],
            display_timezone=cfg["DISPLAY_TIMEZONE"],
            business_start_hour=cfg["BUSINESS_START_HOUR"],
            business_end_hour=cfg["BUSINESS_END_HOUR"],
            slot_minutes=cfg["SLOT_MINUTES"],
            max_consecutive_slots=cfg["MAX_CONSECUTIVE_SLOTS"],
            available_weekdays=tuple(cfg["AVAILABLE_WEEKDAYS"]),
            booking_horizon_days=cfg["BOOKING_HORIZON_DAYS"],
            min_notice_hours=cfg["MIN_NOTICE_HOURS"],
        )

    @property
    def business_tz(self) -> ZoneInfo:
        return ZoneInfo(self.business_timezone)

    @property
    def display_tz(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)

    @property
    def slot_length(self) -> timedelta:
        return timedelta(minutes=self.slot_minutes)

    @property
    def max_minutes(self) -> int:
        return self.slot_minutes * self.max_consecutive_slots

    @property
    def offers_longer_meetings(self) -> bool:
        return self.max_consecutive_slots > 1
