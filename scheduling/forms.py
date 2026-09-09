"""Forms for the server-rendered booking pages.

`start_at` is a ChoiceField whose options are the currently-available slots, so
Django rejects any slot that isn't genuinely open (including one taken since the
page loaded).
"""

from datetime import datetime

from django import forms

SlotChoices = list[tuple[str, str]]


class _SlotForm(forms.Form):
    start_at = forms.ChoiceField(widget=forms.RadioSelect)

    def __init__(self, *args, slot_choices: SlotChoices | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_at"].choices = slot_choices or []

    def clean_start_at(self) -> datetime:
        try:
            return datetime.fromisoformat(self.cleaned_data["start_at"])
        except ValueError as exc:
            raise forms.ValidationError("Invalid time slot.") from exc


class BookingForm(_SlotForm):
    start_at = forms.ChoiceField(widget=forms.RadioSelect, label="Available times")
    client_name = forms.CharField(max_length=120, label="Your name")
    client_email = forms.EmailField(label="Your email")
    note = forms.CharField(
        required=False,
        max_length=1000,
        label="Anything we should know? (optional)",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class RescheduleForm(_SlotForm):
    start_at = forms.ChoiceField(widget=forms.RadioSelect, label="New time")
