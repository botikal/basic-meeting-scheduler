"""Shared test fixtures: an isolated in-memory DB and overridden settings."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.config import Settings, get_settings
from app.database import get_session
from app.main import app
from app.timeutils import now_utc


@pytest.fixture
def settings() -> Settings:
    return Settings(
        timezone="UTC",
        business_start_hour=9,
        business_end_hour=17,
        slot_minutes=30,
        available_weekdays=[0, 1, 2, 3, 4],
        booking_horizon_days=60,
        min_notice_hours=0,
        admin_username="admin",
        admin_password="secret",
        smtp_host="",
        base_url="http://testserver",
    )


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(session, settings):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def slot(settings) -> datetime:
    """A valid, bookable slot: the next available weekday at opening time."""
    return _slot_on_offset(settings, day_offset=1)


@pytest.fixture
def other_slot(settings) -> datetime:
    """A second valid slot, one hour after `slot`."""
    return _slot_on_offset(settings, day_offset=1) + timedelta(hours=1)


def _slot_on_offset(settings: Settings, day_offset: int) -> datetime:
    day = (now_utc() + timedelta(days=day_offset)).date()
    while day.weekday() not in settings.available_weekdays:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, settings.business_start_hour, 0)
