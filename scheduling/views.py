"""Server-rendered pages: the client booking flow and the manage page."""

from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from .availability import available_slots
from .forms import BookingForm, RescheduleForm
from .models import Booking
from .rules import Rules
from .services import (
    SlotUnavailable,
    cancel_booking,
    create_booking,
    reschedule_booking,
)


def _parse_day(request) -> date | None:
    raw = request.GET.get("day") or request.POST.get("day")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _slot_choices(day, rules, *, ignore_start=None):
    slots = available_slots(day, rules, ignore_start=ignore_start)
    return [(s.isoformat(), s.astimezone(rules.tz).strftime("%a %d %b %Y, %H:%M")) for s in slots]


def index(request):
    rules = Rules.current()
    day = _parse_day(request)
    choices = _slot_choices(day, rules) if day else []
    return render(
        request,
        "scheduling/index.html",
        {
            "rules": rules,
            "day": day,
            "form": BookingForm(slot_choices=choices),
            "has_day": day is not None,
            "slots_exist": bool(choices),
        },
    )


def book(request):
    if request.method != "POST":
        return redirect("scheduling:index")

    rules = Rules.current()
    day = _parse_day(request)
    choices = _slot_choices(day, rules) if day else []
    form = BookingForm(request.POST, slot_choices=choices)

    if form.is_valid():
        try:
            booking = create_booking(
                client_name=form.cleaned_data["client_name"],
                client_email=form.cleaned_data["client_email"],
                start_at=form.cleaned_data["start_at"],
                note=form.cleaned_data["note"],
                rules=rules,
            )
            return redirect(booking.get_absolute_url())
        except SlotUnavailable as exc:
            form.add_error(None, str(exc))

    return render(
        request,
        "scheduling/index.html",
        {
            "rules": rules,
            "day": day,
            "form": form,
            "has_day": day is not None,
            "slots_exist": bool(choices),
        },
    )


def manage(request, token):
    rules = Rules.current()
    booking = get_object_or_404(Booking, manage_token=token)
    day = _parse_day(request)
    choices = _slot_choices(day, rules, ignore_start=booking.start_at) if day else []
    return render(
        request,
        "scheduling/manage.html",
        _manage_context(rules, booking, day, choices, RescheduleForm(slot_choices=choices)),
    )


def reschedule(request, token):
    if request.method != "POST":
        return redirect("scheduling:manage", token=token)

    rules = Rules.current()
    booking = get_object_or_404(Booking, manage_token=token)
    day = _parse_day(request)
    choices = _slot_choices(day, rules, ignore_start=booking.start_at) if day else []
    form = RescheduleForm(request.POST, slot_choices=choices)

    if form.is_valid():
        try:
            reschedule_booking(booking, form.cleaned_data["start_at"], rules)
            messages.success(request, "Your meeting has been moved.")
            return redirect("scheduling:manage", token=token)
        except SlotUnavailable as exc:
            form.add_error(None, str(exc))

    return render(
        request,
        "scheduling/manage.html",
        _manage_context(rules, booking, day, choices, form),
    )


def cancel(request, token):
    booking = get_object_or_404(Booking, manage_token=token)
    if request.method == "POST":
        cancel_booking(booking)
        messages.success(request, "Your meeting has been cancelled.")
    return redirect("scheduling:manage", token=token)


def _manage_context(rules, booking, day, choices, form):
    return {
        "rules": rules,
        "booking": booking,
        "when": booking.start_at.astimezone(rules.tz).strftime("%a %d %b %Y, %H:%M"),
        "day": day,
        "form": form,
        "has_day": day is not None,
        "slots_exist": bool(choices),
    }
