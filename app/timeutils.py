"""Time helpers.

The whole backend stores and compares datetimes as *naive UTC* (no tzinfo,
always meaning UTC). SQLite does not preserve timezone info, so keeping one
convention everywhere avoids "can't compare aware and naive" bugs.
"""

from datetime import UTC, datetime


def now_utc() -> datetime:
    """Current time as naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_naive(dt: datetime) -> datetime:
    """Normalize any datetime to naive UTC.

    Aware datetimes are converted; naive ones are assumed to already be UTC.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt
