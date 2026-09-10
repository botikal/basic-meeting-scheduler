"""Server-rendered booking flow (progressively enhanced with htmx).

Every interactive step is a plain GET with query params - ``?month=`` /
``?date=`` / ``?start=`` / ``?slot_count=`` - so the pages work without
JavaScript. htmx just swaps the ``#planner`` region instead of reloading.
"""

from datetime import date, datetime
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .availability import available_slots, consecutive_capacity, local_date_of
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


def _clamped_int(raw, low: int, high: int) -> int:
    try:
        return max(low, min(int(raw), high))
    except TypeError, ValueError:
        return low


def _slot_label(moment: datetime, rules: Rules) -> str:
    return moment.astimezone(rules.tz).strftime("%A %d %B, %H:%M")


def _length_label(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minutes"
    hours, rest = divmod(minutes, 60)
    unit = "hour" if hours == 1 else "hours"
    return f"{hours} {unit}" if rest == 0 else f"{hours}h {rest}m"


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

    exclude_id = booking.pk if booking else None
    need = booking.slot_count if (mode == "reschedule" and booking) else 1

    slots = None
    if selected:
        free = available_slots(selected, rules, exclude_id=exclude_id)
        if need > 1:
            free_set = set(free)
            step = rules.slot_length
            free = [s for s in free if all((s + i * step) in free_set for i in range(need))]
        slots = [
            {
                "iso": s.isoformat(),
                "label": s.astimezone(rules.tz).strftime("%H:%M"),
                "selected": start is not None and s == start,
            }
            for s in free
        ]

    length_options = None
    slot_count = 1
    can_move = True
    if start:
        capacity = consecutive_capacity(start, rules, exclude_id=exclude_id)
        if mode == "book":
            top = max(min(capacity, rules.max_consecutive_slots), 1)
            slot_count = _clamped_int(_param(request, "slot_count"), 1, top)
            length_options = [
                {
                    "value": n,
                    "label": _length_label(n * rules.slot_minutes),
                    "selected": n == slot_count,
                }
                for n in range(1, top + 1)
            ]
        else:
            can_move = capacity >= need

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
        "length_options": length_options,
        "slot_count": slot_count,
        "can_move": can_move,
        "reschedule_length": (_length_label(booking.duration_minutes) if booking else None),
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
                slot_count=_clamped_int(
                    request.POST.get("slot_count"), 1, rules.max_consecutive_slots
                ),
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


# --- Staff area -------------------------------------------------------
# Same accounts as the Django admin (any user with is_staff). The client
# booking flow stays anonymous; this is purely additive.


staff_required = user_passes_test(
    lambda u: u.is_active and u.is_staff,
    login_url="scheduling:staff-login",
)


class StaffLoginView(LoginView):
    template_name = "scheduling/staff_login.html"
    redirect_authenticated_user = True


@staff_required
def staff_home(request):
    rules = Rules.current()
    show_all = request.GET.get("all") == "1"

    bookings = Booking.objects.all()
    if show_all:
        bookings = bookings.order_by("-start_at")
    else:
        bookings = bookings.filter(
            status=Booking.Status.CONFIRMED, end_at__gte=timezone.now()
        ).order_by("start_at")
    rows = list(bookings)

    days = [
        {"date": day, "bookings": list(items)}
        for day, items in groupby(rows, key=lambda b: local_date_of(b.start_at, rules))
    ]
    return render(
        request,
        "scheduling/staff_home.html",
        {"rules": rules, "days": days, "count": len(rows), "show_all": show_all},
    )


@staff_required
@require_POST
def staff_cancel(request, token):
    booking = get_object_or_404(Booking, manage_token=token)
    cancel_booking(booking)
    messages.success(request, f"Cancelled {booking.client_name}'s booking.")
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/staff/") else "scheduling:staff-home")
