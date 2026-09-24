from django.contrib import admin

from .models import (
    ActivityLog,
    AgentJob,
    AuditEvent,
    BreachEvent,
    Broker,
    ConsentRecord,
    DataStopRequest,
    EmailVerification,
    Exposure,
    Household,
    HouseholdMember,
    Identity,
    IdentityIdentifier,
    MonitorRun,
    Notification,
    NotificationChannelConfig,
    PushSubscription,
    RemovalCampaign,
    RemovalEvidence,
    RemovalRequest,
    Scan,
    TwoFactorDevice,
    UserProfile,
    Watchlist,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "city", "state", "created_at"]
    list_filter = ["plan"]
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
    list_display = ["action", "user", "scan", "timestamp"]
    list_filter = ["action"]
    readonly_fields = ["user", "scan", "action", "details", "timestamp"]


# --- Sentinel / security admin -------------------------------------------
class IdentityIdentifierInline(admin.TabularInline):
    model = IdentityIdentifier
    extra = 0
    readonly_fields = ["kind", "masked_value", "blind_index", "is_verified", "created_at"]
    can_delete = False


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ["label", "user", "is_primary", "is_dependent", "household", "created_at"]
    list_filter = ["is_primary", "is_dependent"]
    search_fields = ["label", "user__username"]
    inlines = [IdentityIdentifierInline]


class HouseholdMemberInline(admin.TabularInline):
    model = HouseholdMember
    extra = 0


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "created_at"]
    search_fields = ["name", "owner__username"]
    inlines = [HouseholdMemberInline]


@admin.register(HouseholdMember)
class HouseholdMemberAdmin(admin.ModelAdmin):
    list_display = ["household", "display_name", "user", "role", "can_manage"]
    list_filter = ["role"]


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "is_active", "cadence_hours", "next_run_at"]
    list_filter = ["is_active"]


@admin.register(MonitorRun)
class MonitorRunAdmin(admin.ModelAdmin):
    list_display = ["watchlist", "status", "findings_count", "started_at", "completed_at"]
    list_filter = ["status"]


@admin.register(Exposure)
class ExposureAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "kind", "severity", "status", "source", "last_seen"]
    list_filter = ["kind", "severity", "status", "source"]
    search_fields = ["title", "site_domain", "user__username"]
    readonly_fields = ["fingerprint", "matched_blind_index", "first_seen", "last_seen"]


@admin.register(BreachEvent)
class BreachEventAdmin(admin.ModelAdmin):
    list_display = ["breach_name", "source", "breach_date", "pwn_count"]
    list_filter = ["source"]


@admin.register(RemovalCampaign)
class RemovalCampaignAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "channel", "status", "broker", "deadline_at"]
    list_filter = ["channel", "status"]
    search_fields = ["user__username", "broker__name"]


@admin.register(AgentJob)
class AgentJobAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "job_type", "status", "attempts", "created_at"]
    list_filter = ["job_type", "status"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "severity", "is_read", "created_at"]
    list_filter = ["severity", "is_read"]


@admin.register(NotificationChannelConfig)
class NotificationChannelConfigAdmin(admin.ModelAdmin):
    list_display = ["kind", "user", "is_active", "severity_threshold", "created_at"]
    list_filter = ["kind", "is_active"]


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "endpoint", "is_active", "last_used_at", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["user__username", "endpoint"]


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ["user", "scope", "granted", "policy_version", "updated_at"]
    list_filter = ["scope", "granted"]


@admin.register(TwoFactorDevice)
class TwoFactorDeviceAdmin(admin.ModelAdmin):
    list_display = ["user", "is_enabled", "confirmed_at", "last_used_at"]
    list_filter = ["is_enabled"]
    readonly_fields = ["secret"]


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ["user", "is_verified", "created_at", "verified_at"]
    list_filter = ["is_verified"]


@admin.register(RemovalEvidence)
class RemovalEvidenceAdmin(admin.ModelAdmin):
    list_display = ["campaign", "kind", "sha256", "created_at"]
    readonly_fields = ["ciphertext", "sha256"]


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["action", "user", "ip", "created_at"]
    list_filter = ["action"]
    search_fields = ["action", "user__username"]
    readonly_fields = ["user", "action", "ip", "user_agent", "metadata", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
