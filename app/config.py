"""Application configuration.

All settings can be overridden with environment variables or a `.env` file
(see `.env.example`). Complex values like `available_weekdays` must be given as
JSON in the environment, e.g. AVAILABLE_WEEKDAYS=[0,1,2,3,4].
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Meeting Scheduler"
    # Public base URL, used to build the "manage your booking" links in emails.
    base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./scheduler.db"

    # Shown to clients as who they are meeting with.
    host_name: str = "Our Team"

    # --- Availability rules -------------------------------------------------
    # IANA timezone the business hours below are expressed in.
    timezone: str = "UTC"
    business_start_hour: int = 9  # 09:00
    business_end_hour: int = 17  # 17:00 (last slot ends by this time)
    slot_minutes: int = 30
    available_weekdays: list[int] = [0, 1, 2, 3, 4]  # Mon=0 .. Sun=6
    booking_horizon_days: int = 14  # how far ahead clients may book
    min_notice_hours: int = 2  # no bookings sooner than this

    # --- Staff (admin) auth ----------------------------------------------
    admin_username: str = "admin"
    admin_password: str = "change-me"

    # --- Email (optional; prints to console when smtp_host is empty) ------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = "scheduler@example.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
