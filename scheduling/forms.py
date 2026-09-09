"""Forms for the booking pages.

The chosen time comes from a hidden `start` field and is validated server-side
by `services.create_booking` / `reschedule_booking`; this form only covers the
client's own details.
"""

from django import forms


class BookingDetailsForm(forms.Form):
    client_name = forms.CharField(max_length=120, label="Your name")
    client_email = forms.EmailField(label="Your email")
    note = forms.CharField(
        required=False,
        max_length=1000,
        label="Anything we should know? (optional)",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
