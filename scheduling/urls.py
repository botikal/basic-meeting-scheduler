"""URL patterns for the scheduling app."""

from django.urls import path

from . import api, views

app_name = "scheduling"

urlpatterns = [
    # Client-facing pages
    path("", views.index, name="index"),
    path("book/", views.book, name="book"),
    path("b/<str:token>/", views.manage, name="manage"),
    path("b/<str:token>/reschedule/", views.reschedule, name="reschedule"),
    path("b/<str:token>/cancel/", views.cancel, name="cancel"),
    # JSON API
    path("api/slots/", api.slots, name="api-slots"),
    path("api/bookings/", api.create_booking_view, name="api-create"),
    path("api/bookings/<str:token>/", api.booking_detail, name="api-detail"),
    path("api/bookings/<str:token>/reschedule/", api.reschedule_view, name="api-reschedule"),
    path("api/bookings/<str:token>/cancel/", api.cancel_view, name="api-cancel"),
]
