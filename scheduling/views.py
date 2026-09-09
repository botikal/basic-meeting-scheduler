"""Server-rendered booking flow (progressively enhanced with htmx).

Every interactive step is a plain GET with query params - ``?month=`` /
``?date=`` / ``?start=`` - so the pages work without JavaScript. htmx just swaps
the ``#planner`` region instead of reloading the whole page.
"""

from datetime import date, datetime

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .availability import available_slots, local_date_of
from .calendarview import WEEKDAY_LABELS, build_month, parse_month
from .forms import BookingDetailsForm
from .models import Booking
from .rules import Rules
from .services import (
    SlotUnavailable,
    cancel_booking,
    create_booking,
    reschedule_booking,
)


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _param(request, name: str) -> str | None:
    return request.POST.get(name) or request.GET.get(name)


def _parse_date(raw: str | None) -> date | None:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _parse_start(raw: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _slot_label(moment: datetime, rules: Rules) -> str:
    return moment.astimezone(rules.tz).strftime("%A %d %B, %H:%M")


def _planner_context(
    request,
    rules: Rules,
    *,
    mode: str,
    action_url: str,
    nav_url: str,
    selected: date | None,
    start: datetime | None,
    booking: Booking | None = None,
    form: BookingDetailsForm | None = None,
    form_error: str | None = None,
) -> dict:
    raw_month = _param(request, "month")
    if raw_month:
        year, month = parse_month(raw_month)
    elif selected:
        year, month = selected.year, selected.month
    else:
        year, month = parse_month(None)

    ignore_start = booking.start_at if booking else None
    slots = None
    if selected:
        slots = [
            {
                "iso": s.isoformat(),
                "label": s.astimezone(rules.tz).strftime("%H:%M"),
                "selected": start is not None and s == start,
            }
            for s in available_slots(selected, rules, ignore_start=ignore_start)
        ]

    return {
        "rules": rules,
        "mode": mode,
        "action_url": action_url,
        "nav_url": nav_url,
        "month": build_month(year, month, rules, selected),
        "weekday_labels": WEEKDAY_LABELS,
        "selected": selected,
        "slots": slots,
        "start": start,
        "start_label": _slot_label(start, rules) if start else None,
        "booking": booking,
        "form": form if form is not None else BookingDetailsForm(),
        "form_error": form_error,
    }


def _render_planner(request, page_template: str, context: dict, *, status: int = 200):
    template = "scheduling/_planner.html" if _is_htmx(request) else page_template
    return render(request, template, context, status=status)


# --- Booking -------------------------------------------------------------


def index(request):
    rules = Rules.current()
    start = _parse_start(request.GET.get("start"))
    selected = _parse_date(request.GET.get("date")) or (
        local_date_of(start, rules) if start else None
    )
    context = _planner_context(
        request,
        rules,
        mode="book",
        action_url=reverse("scheduling:book"),
        nav_url=reverse("scheduling:index"),
        selected=selected,
        start=start,
    )
    return _render_planner(request, "scheduling/index.html", context)


def book(request):
    if request.method != "POST":
        return redirect("scheduling:index")

    rules = Rules.current()
    start = _parse_start(request.POST.get("start"))
    selected = local_date_of(start, rules) if start else None
    form = BookingDetailsForm(request.POST)
    error = None

    if start is None:
        error = "Please pick a time."
    elif form.is_valid():
        try:
            booking = create_booking(
                client_name=form.cleaned_data["client_name"],
                client_email=form.cleaned_data["client_email"],
                start_at=start,
                note=form.cleaned_data["note"],
                rules=rules,
            )
            return _redirect(request, booking.get_absolute_url())
        except SlotUnavailable as exc:
            error = str(exc)

    context = _planner_context(
        request,
        rules,
        mode="book",
        action_url=reverse("scheduling:book"),
        nav_url=reverse("scheduling:index"),
        selected=selected,
        start=start,
        form=form,
        form_error=error,
    )
    return _render_planner(request, "scheduling/index.html", context)


# --- Manage / reschedule / cancel --------------------------------------


def manage(request, token):
    rules = Rules.current()
    booking = get_object_or_404(Booking, manage_token=token)
    start = _parse_start(request.GET.get("start"))
    selected = _parse_date(request.GET.get("date")) or (
        local_date_of(start, rules) if start else None
    )
    context = _planner_context(
        request,
        rules,
        mode="reschedule",
        action_url=reverse("scheduling:reschedule", args=[token]),
        nav_url=reverse("scheduling:manage", args=[token]),
        selected=selected,
        start=start,
        booking=booking,
    )
    context["when"] = _slot_label(booking.start_at, rules)
    return _render_planner(request, "scheduling/manage.html", context)


def reschedule(request, token):
    if request.method != "POST":
        return redirect("scheduling:manage", token=token)

    rules = Rules.current()
    booking = get_object_or_404(Booking, manage_token=token)
    start = _parse_start(request.POST.get("start"))
    try:
        if start is None:
            raise SlotUnavailable("Please pick a time.")
        reschedule_booking(booking, start, rules)
        messages.success(request, "Your meeting has been moved.")
    except SlotUnavailable as exc:
        messages.error(request, str(exc))
    return _redirect(request, reverse("scheduling:manage", args=[token]))


def cancel(request, token):
    booking = get_object_or_404(Booking, manage_token=token)
    if request.method == "POST":
        cancel_booking(booking)
        messages.success(request, "Your meeting has been cancelled.")
    return _redirect(request, reverse("scheduling:manage", args=[token]))


def _redirect(request, url: str):
    """Redirect that also works as an htmx response."""
    if _is_htmx(request):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)
