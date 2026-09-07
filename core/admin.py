from django.contrib import admin
from .models import (
    UserProfile,
    Broker,
    Scan,
    RemovalRequest,
    DataStopRequest,
    ActivityLog,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "city", "state", "created_at"]
    search_fields = ["user__username", "user__email", "user__first_name"]


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "removal_method", "is_active", "priority"]
    list_filter = ["category", "removal_method", "is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


class RemovalRequestInline(admin.TabularInline):
    model = RemovalRequest
    extra = 0
    readonly_fields = ["broker", "status", "method", "found_url", "created_at"]


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "full_name",
        "email",
        "status",
        "progress_percent",
        "found_count",
        "removed_count",
        "created_at",
    ]
    list_filter = ["status", "is_recurring"]
    search_fields = ["full_name", "email"]
    readonly_fields = [
        "id",
        "total_brokers",
        "completed_brokers",
        "found_count",
        "removed_count",
        "pending_count",
        "failed_count",
    ]
    inlines = [RemovalRequestInline]


@admin.register(RemovalRequest)
class RemovalRequestAdmin(admin.ModelAdmin):
    list_display = ["broker", "scan", "status", "method", "retry_count", "created_at"]
    list_filter = ["status", "method"]
    search_fields = ["broker__name", "scan__full_name"]


@admin.register(DataStopRequest)
class DataStopRequestAdmin(admin.ModelAdmin):
    list_display = ["broker", "user", "status", "stop_selling", "created_at"]
    list_filter = ["status", "stop_selling", "stop_sharing"]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["action", "scan", "timestamp"]
    list_filter = ["action"]
    readonly_fields = ["scan", "action", "details", "timestamp"]
