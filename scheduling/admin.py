"""Staff-facing admin for bookings."""

from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        "start_at",
        "end_at",
        "client_name",
        "client_email",
        "status",
        "created_at",
    ]
    list_filter = ["status", "start_at"]
    search_fields = ["client_name", "client_email", "manage_token"]
    readonly_fields = ["manage_token", "created_at", "calendar_event_id", "meet_url"]
    date_hierarchy = "start_at"
    ordering = ["-start_at"]
