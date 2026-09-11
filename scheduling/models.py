"""Database models."""

from secrets import token_urlsafe

from django.db import models
from django.urls import reverse


def _new_token() -> str:
    """A ~43-char URL-safe random token used in the private manage link."""
    return token_urlsafe(32)


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    manage_token = models.CharField(max_length=64, unique=True, default=_new_token, editable=False)
    client_name = models.CharField(max_length=120)
    client_email = models.EmailField()
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    # Number of back-to-back slots this booking occupies (1 = a single slot).
    slot_count = models.PositiveSmallIntegerField(default=1)
    note = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)

    # Set once a Google Calendar event has been created for this booking.
    # Blank when Google Calendar isn't configured, or the API call failed.
    calendar_event_id = models.CharField(max_length=255, blank=True, default="")
    meet_url = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["start_at"]
        constraints = [
            # At most one confirmed booking may occupy a given start time.
            # Cancelled rows are exempt, so a freed slot can be re-booked.
            models.UniqueConstraint(
                fields=["start_at"],
                condition=models.Q(status="confirmed"),
                name="unique_confirmed_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_name} @ {self.start_at:%Y-%m-%d %H:%M} ({self.status})"

    @property
    def is_confirmed(self) -> bool:
        return self.status == self.Status.CONFIRMED

    @property
    def duration_minutes(self) -> int:
        return round((self.end_at - self.start_at).total_seconds() / 60)

    def get_absolute_url(self) -> str:
        return reverse("scheduling:manage", args=[self.manage_token])
