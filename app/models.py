"""Database tables and API schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import EmailStr
from sqlmodel import Field, SQLModel

from .timeutils import now_utc


def _new_token() -> str:
    """A 32-char random hex token (~128 bits) used in manage links."""
    return uuid4().hex


class BookingStatus(StrEnum):
    confirmed = "confirmed"
    cancelled = "cancelled"


class Booking(SQLModel, table=True):
    """A single booked meeting slot."""

    id: int | None = Field(default=None, primary_key=True)
    manage_token: str = Field(default_factory=_new_token, index=True, unique=True)
    client_name: str
    client_email: str
    # Naive UTC. start_at is the slot; end_at = start_at + slot length.
    start_at: datetime = Field(index=True)
    end_at: datetime
    note: str = ""
    status: BookingStatus = Field(default=BookingStatus.confirmed, index=True)
    created_at: datetime = Field(default_factory=now_utc)


# --- API request/response schemas ---------------------------------------


class BookingCreate(SQLModel):
    client_name: str = Field(min_length=1, max_length=120)
    client_email: EmailStr
    start_at: datetime
    note: str = Field(default="", max_length=1000)


class BookingReschedule(SQLModel):
    start_at: datetime


class BookingRead(SQLModel):
    client_name: str
    client_email: str
    start_at: datetime
    end_at: datetime
    note: str
    status: BookingStatus
    manage_token: str
    manage_url: str
