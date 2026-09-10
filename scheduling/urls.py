"""URL patterns for the scheduling app."""

from django.contrib.auth import views as auth_views
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
    # Staff area
    path("staff/", views.staff_home, name="staff-home"),
    path("staff/login/", views.StaffLoginView.as_view(), name="staff-login"),
    path(
        "staff/logout/",
        auth_views.LogoutView.as_view(next_page="scheduling:staff-login"),
        name="staff-logout",
    ),
    path("staff/b/<str:token>/cancel/", views.staff_cancel, name="staff-cancel"),
    # JSON API
    path("api/slots/", api.slots, name="api-slots"),
    path("api/bookings/", api.create_booking_view, name="api-create"),
    path("api/bookings/<str:token>/", api.booking_detail, name="api-detail"),
    path("api/bookings/<str:token>/reschedule/", api.reschedule_view, name="api-reschedule"),
    path("api/bookings/<str:token>/cancel/", api.cancel_view, name="api-cancel"),
]
