"""The visitor's own timezone, detected client-side.

base.html runs a small script that reads the browser's IANA timezone
(`Intl.DateTimeFormat().resolvedOptions().timeZone`) and stores it in a `tz`
cookie. This reads that cookie back, so client-facing pages can show times in
the visitor's own zone instead of a fixed default.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

COOKIE_NAME = "tz"


def client_timezone(request) -> str | None:
    """A validated IANA timezone name from the visitor's cookie, or None."""
    raw = request.COOKIES.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        ZoneInfo(raw)
    except ZoneInfoNotFoundError, ValueError:
        return None
    return raw
