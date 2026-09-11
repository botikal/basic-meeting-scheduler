"""Confirmation / cancellation emails.

With no EMAIL_HOST configured (the default), Django's console backend prints
these to the terminal instead of sending them.
"""

from django.core.mail import send_mail

from .models import Booking
from .rules import Rules


def _when(booking: Booking, rules: Rules) -> str:
    start = booking.start_at.astimezone(rules.display_tz)
    end = booking.end_at.astimezone(rules.display_tz)
    return (
        start.strftime("%A, %d %B %Y, %H:%M")
        + end.strftime("-%H:%M ")
        + rules.display_timezone
        + f" ({booking.duration_minutes} minutes)"
    )


def _manage_url(booking: Booking, rules: Rules) -> str:
    return f"{rules.base_url}/b/{booking.manage_token}"


def send_confirmation(booking: Booking) -> None:
    rules = Rules.current()
    meet_line = (
        f"Join by Google Meet:\n  {booking.meet_url}\n"
        f"(you'll also get a separate calendar invite from Google)\n\n"
        if booking.meet_url
        else ""
    )
    body = (
        f"Hi {booking.client_name},\n\n"
        f"Your meeting with {rules.host_name} is confirmed for:\n"
        f"  {_when(booking, rules)}\n\n"
        f"{meet_line}"
        f"Need to reschedule or cancel? Use this private link:\n"
        f"  {_manage_url(booking, rules)}\n\n"
        f"Do not share the link - it is the key to managing this booking.\n"
    )
    send_mail(
        subject=f"Meeting confirmed - {_when(booking, rules)}",
        message=body,
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=[booking.client_email],
    )


def send_cancellation(booking: Booking) -> None:
    rules = Rules.current()
    body = (
        f"Hi {booking.client_name},\n\n"
        f"Your meeting with {rules.host_name} on {_when(booking, rules)} "
        f"has been cancelled.\n\n"
        f"You can book a new time at {rules.base_url}/\n"
    )
    send_mail(
        subject=f"Meeting cancelled - {_when(booking, rules)}",
        message=body,
        from_email=None,
        recipient_list=[booking.client_email],
    )
