"""Google Calendar integration: one calendar event (with a Meet link) per
confirmed booking.

Entirely optional - if GOOGLE_CALENDAR isn't configured (or an API call
fails), these functions are no-ops and the booking itself still succeeds.
A booking without a Meet link is a lesser experience, not a broken one.

Auth is OAuth2, delegated by the calendar's own owner - the app acts as that
person, so no separate "share this calendar with a robot" step is needed (and
no organization policy on external sharing gets in the way). One-time setup:

    python manage.py google_oauth_setup path/to/client_secret.json

opens a browser for the owner to sign in and approve, then writes
GOOGLE_TOKEN_FILE. See README.md.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from .models import Booking

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _config() -> dict[str, str] | None:
    cfg = settings.GOOGLE_CALENDAR
    if cfg.get("TOKEN_FILE") and cfg.get("CALENDAR_ID"):
        return cfg
    return None


def _service():
    cfg = _config()
    if not cfg:
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(cfg["TOKEN_FILE"], SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(cfg["TOKEN_FILE"], "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_event(booking: Booking) -> tuple[str, str] | None:
    """Create a calendar event with a Meet link for `booking`.

    Returns (event_id, meet_url) on success, or None if Google Calendar isn't
    configured or the request failed.
    """
    cfg = _config()
    if not cfg:
        return None
    try:
        service = _service()
        event = (
            service.events()
            .insert(
                calendarId=cfg["CALENDAR_ID"],
                conferenceDataVersion=1,
                body={
                    "summary": f"Meeting with {booking.client_name}",
                    "description": (
                        f"Booked via the scheduler by {booking.client_name} "
                        f"<{booking.client_email}>.\n\n{booking.note}"
                    ).strip(),
                    "start": {"dateTime": booking.start_at.isoformat()},
                    "end": {"dateTime": booking.end_at.isoformat()},
                    "conferenceData": {
                        "createRequest": {
                            "requestId": uuid.uuid4().hex,
                            "conferenceSolutionKey": {"type": "hangoutsMeet"},
                        }
                    },
                },
            )
            .execute()
        )
    except Exception:
        logger.exception("Google Calendar: could not create an event for booking %s", booking.pk)
        return None

    return event["id"], event.get("hangoutLink", "")


def update_event(booking: Booking) -> None:
    """Move `booking`'s calendar event to its (new) start/end time."""
    if not booking.calendar_event_id:
        return
    cfg = _config()
    if not cfg:
        return
    try:
        service = _service()
        service.events().patch(
            calendarId=cfg["CALENDAR_ID"],
            eventId=booking.calendar_event_id,
            body={
                "start": {"dateTime": booking.start_at.isoformat()},
                "end": {"dateTime": booking.end_at.isoformat()},
            },
        ).execute()
    except Exception:
        logger.exception("Google Calendar: could not update event for booking %s", booking.pk)


def delete_event(booking: Booking) -> None:
    """Remove `booking`'s calendar event (called when it's cancelled)."""
    if not booking.calendar_event_id:
        return
    cfg = _config()
    if not cfg:
        return
    try:
        service = _service()
        service.events().delete(
            calendarId=cfg["CALENDAR_ID"], eventId=booking.calendar_event_id
        ).execute()
    except Exception:
        logger.exception("Google Calendar: could not delete event for booking %s", booking.pk)
