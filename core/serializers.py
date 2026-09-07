from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Broker, Scan, RemovalRequest, DataStopRequest, UserProfile, ActivityLog


class UserSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["phone", "address", "city", "state", "zip_code", "date_of_birth"]


class BrokerSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    removal_method_display = serializers.CharField(source="get_removal_method_display", read_only=True)

    class Meta:
        model = Broker
        fields = [
            "id", "name", "slug", "website_url", "category", "category_display",
            "description", "opt_out_url", "opt_out_email", "removal_method",
            "removal_method_display", "requires_identity", "estimated_days",
        ]


class ScanSerializer(serializers.ModelSerializer):
    progress_percent = serializers.IntegerField(read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = Scan
        fields = [
            "id", "full_name", "email", "phone", "address",
            "status", "progress_percent", "total_brokers", "completed_brokers",
            "found_count", "removed_count", "failed_count",
            "is_recurring", "recurring_interval_days", "next_scan_date",
            "created_at", "completed_at", "user",
        ]

    def get_user(self, obj):
        return obj.user.username


class RemovalRequestSerializer(serializers.ModelSerializer):
    broker = BrokerSerializer(read_only=True)
    broker_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = RemovalRequest
        fields = [
            "id", "broker", "broker_id", "status", "method",
            "found_url", "removal_url", "confirmation_code",
            "error_message", "retry_count", "created_at", "completed_at",
        ]


class DataStopRequestSerializer(serializers.ModelSerializer):
    broker = BrokerSerializer(read_only=True)
    broker_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = DataStopRequest
        fields = [
            "id", "broker", "broker_id", "status",
            "stop_selling", "stop_sharing", "stop_marketing",
            "confirmation_code", "notes", "created_at",
        ]


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = ["id", "action", "details", "timestamp"]