"""Sending confirmation / cancellation emails.

If `settings.smtp_host` is empty (the default), emails are printed to the
console instead of sent - handy in development.
"""

import smtplib
from email.message import EmailMessage

from .config import Settings
from .models import Booking


def _format_when(booking: Booking, settings: Settings) -> str:
    from zoneinfo import ZoneInfo

    local = booking.start_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(settings.timezone))
    return local.strftime("%A, %d %B %Y at %H:%M ") + settings.timezone


def send_email(to: str, subject: str, body: str, settings: Settings) -> None:
    if not settings.smtp_host:
        print(
            f"\n----- EMAIL (dev, not sent) -----\n"
            f"To: {to}\nSubject: {subject}\n\n{body}\n"
            f"---------------------------------\n"
        )
        return

    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


def send_booking_confirmation(booking: Booking, settings: Settings) -> None:
    manage_url = f"{settings.base_url.rstrip('/')}/b/{booking.manage_token}"
    body = (
        f"Hi {booking.client_name},\n\n"
        f"Your meeting with {settings.host_name} is confirmed for:\n"
        f"  {_format_when(booking, settings)}\n\n"
        f"Need to reschedule or cancel? Use this private link:\n"
        f"  {manage_url}\n\n"
        f"Do not share the link - it is the key to managing this booking.\n"
    )
    send_email(
        booking.client_email,
        f"Meeting confirmed - {_format_when(booking, settings)}",
        body,
        settings,
    )


def send_booking_cancellation(booking: Booking, settings: Settings) -> None:
    body = (
        f"Hi {booking.client_name},\n\n"
        f"Your meeting with {settings.host_name} on "
        f"{_format_when(booking, settings)} has been cancelled.\n\n"
        f"You can book a new time at {settings.base_url.rstrip('/')}/\n"
    )
    send_email(
        booking.client_email,
        f"Meeting cancelled - {_format_when(booking, settings)}",
        body,
        settings,
    )
