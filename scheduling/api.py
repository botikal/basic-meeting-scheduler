"""JSON API endpoints (Django REST Framework)."""

from datetime import date

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from .availability import available_slots
from .models import Booking
from .rules import Rules
from .serializers import (
    BookingCreateSerializer,
    BookingSerializer,
    RescheduleSerializer,
)
from .services import SlotUnavailable, cancel_booking, create_booking, reschedule_booking


@api_view(["GET"])
def slots(request):
    raw = request.query_params.get("day")
    if not raw:
        return Response(
            {"detail": "query param 'day' (YYYY-MM-DD) is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        return Response(
            {"detail": "invalid 'day'; use YYYY-MM-DD"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    rules = Rules.current()
    return Response(
        {
            "day": day.isoformat(),
            "slots": [s.isoformat() for s in available_slots(day, rules)],
        }
    )


@api_view(["POST"])
def create_booking_view(request):
    serializer = BookingCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        booking = create_booking(**serializer.validated_data)
    except SlotUnavailable as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def booking_detail(request, token):
    booking = get_object_or_404(Booking, manage_token=token)
    return Response(BookingSerializer(booking).data)


@api_view(["POST"])
def reschedule_view(request, token):
    booking = get_object_or_404(Booking, manage_token=token)
    serializer = RescheduleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        reschedule_booking(booking, serializer.validated_data["start_at"])
    except SlotUnavailable as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(BookingSerializer(booking).data)


@api_view(["POST"])
def cancel_view(request, token):
    booking = get_object_or_404(Booking, manage_token=token)
    cancel_booking(booking)
    return Response(BookingSerializer(booking).data)
