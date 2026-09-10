"""DRF serializers for the JSON API."""

from rest_framework import serializers

from .models import Booking
from .rules import Rules


class BookingSerializer(serializers.ModelSerializer):
    manage_url = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "client_name",
            "client_email",
            "start_at",
            "end_at",
            "slot_count",
            "note",
            "status",
            "manage_token",
            "manage_url",
        ]

    def get_manage_url(self, obj: Booking) -> str:
        return f"{Rules.current().base_url}/b/{obj.manage_token}"


class BookingCreateSerializer(serializers.Serializer):
    client_name = serializers.CharField(max_length=120)
    client_email = serializers.EmailField()
    start_at = serializers.DateTimeField()
    slot_count = serializers.IntegerField(required=False, default=1, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


class RescheduleSerializer(serializers.Serializer):
    start_at = serializers.DateTimeField()
    slot_count = serializers.IntegerField(required=False, allow_null=True, min_value=1)
