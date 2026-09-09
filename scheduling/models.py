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
    note = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)

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

    def get_absolute_url(self) -> str:
        return reverse("scheduling:manage", args=[self.manage_token])
