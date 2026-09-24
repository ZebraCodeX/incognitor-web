from django.contrib.auth.models import User
from rest_framework import serializers

from .crypto import blind_index, encrypt_text, mask_identifier
from .models import (
    ActivityLog,
    AgentJob,
    AuditEvent,
    BreachEvent,
    Broker,
    ConsentRecord,
    DataStopRequest,
    Exposure,
    Household,
    HouseholdMember,
    Identity,
    IdentityIdentifier,
    Notification,
    NotificationChannelConfig,
    PushSubscription,
    RemovalCampaign,
    RemovalEvidence,
    RemovalRequest,
    Scan,
    UserProfile,
    Watchlist,
)


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
            "compliance_score", "removal_rate",
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


# ===========================================================================
# Sentinel API serializers
# ===========================================================================
class IdentityIdentifierSerializer(serializers.ModelSerializer):
    value = serializers.CharField(write_only=True, required=False, allow_blank=True)
    value_ciphertext = serializers.CharField(write_only=True, required=False, allow_blank=True)
    blind_index = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = IdentityIdentifier
        fields = [
            "id", "kind", "masked_value", "is_verified", "created_at",
            "role", "linked_broker", "triggered_at",
            "value", "value_ciphertext", "blind_index",
        ]
        read_only_fields = ["id", "masked_value", "created_at", "triggered_at"]

    def create(self, validated_data):
        plaintext = validated_data.pop("value", "")
        ciphertext = validated_data.pop("value_ciphertext", "")
        kind = validated_data.get("kind", "other")
        if plaintext:
            validated_data["blind_index"] = blind_index(kind, plaintext)
            validated_data["masked_value"] = mask_identifier(kind, plaintext)
            validated_data["value_encrypted"] = None  # server discards plaintext
        elif ciphertext:
            if not validated_data.get("blind_index"):
                raise serializers.ValidationError(
                    "blind_index is required when supplying value_ciphertext"
                )
            validated_data["value_encrypted"] = ciphertext.encode("utf-8")
        else:
            raise serializers.ValidationError("Provide either 'value' or 'value_ciphertext'")
        return super().create(validated_data)


class IdentitySerializer(serializers.ModelSerializer):
    identifiers = IdentityIdentifierSerializer(many=True, required=False)

    class Meta:
        model = Identity
        fields = ["id", "label", "is_primary", "is_dependent", "household", "created_at", "identifiers"]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        identifiers = validated_data.pop("identifiers", [])
        identity = Identity.objects.create(
            user=self.context["request"].user, **validated_data
        )
        for item in identifiers:
            serializer = IdentityIdentifierSerializer(data=item)
            serializer.is_valid(raise_exception=True)
            plaintext = serializer.validated_data.pop("value", "")
            ciphertext = serializer.validated_data.pop("value_ciphertext", "")
            kind = serializer.validated_data.get("kind", "other")
            if plaintext:
                serializer.validated_data["blind_index"] = blind_index(kind, plaintext)
                serializer.validated_data["masked_value"] = mask_identifier(kind, plaintext)
            elif ciphertext:
                serializer.validated_data["value_encrypted"] = ciphertext.encode("utf-8")
            IdentityIdentifier.objects.create(identity=identity, **serializer.validated_data)
        return identity


class WatchlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Watchlist
        fields = [
            "id", "name", "identity", "is_active", "cadence_hours",
            "include_breaches", "include_web_search", "include_pastes",
            "last_run_at", "next_run_at", "created_at",
        ]
        read_only_fields = ["id", "last_run_at", "next_run_at", "created_at"]


class BreachEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = BreachEvent
        fields = [
            "id", "source", "breach_name", "breach_date", "description",
            "data_classes", "pwn_count", "is_verified",
        ]


class ExposureSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    broker = serializers.SerializerMethodField()

    class Meta:
        model = Exposure
        fields = [
            "id", "kind", "kind_display", "severity", "status", "title", "source",
            "url", "site_domain", "matched_identifier_kind", "masked_evidence",
            "confidence", "provenance", "first_seen", "last_seen", "metadata", "broker",
        ]
        read_only_fields = fields

    def get_broker(self, obj):
        return None


class RemovalEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = RemovalEvidence
        fields = ["id", "kind", "sha256", "metadata", "created_at"]
        read_only_fields = ["id", "sha256", "created_at"]


class RemovalCampaignSerializer(serializers.ModelSerializer):
    broker_name = serializers.CharField(source="broker.name", read_only=True, default="")
    exposure_title = serializers.CharField(source="exposure.title", read_only=True, default="")
    evidence = RemovalEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = RemovalCampaign
        fields = [
            "id", "channel", "status", "jurisdiction", "broker", "broker_name",
            "exposure", "exposure_title", "attempts", "max_attempts",
            "confirmation_code", "error_message", "requested_at", "deadline_at",
            "submitted_at", "completed_at", "created_at", "evidence",
        ]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "body", "severity", "exposure", "is_read", "created_at"]
        read_only_fields = ["id", "title", "body", "severity", "exposure", "created_at"]


class NotificationChannelConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationChannelConfig
        fields = [
            "id", "kind", "target", "is_active", "severity_threshold", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"target": {"write_only": True}}

    def create(self, validated_data):
        target = validated_data.pop("target", "")
        validated_data["target"] = encrypt_text(target).decode("ascii")
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "target" in validated_data:
            validated_data["target"] = encrypt_text(validated_data["target"]).decode("ascii")
        return super().update(instance, validated_data)


class PushSubscriptionSerializer(serializers.ModelSerializer):
    keys = serializers.DictField(write_only=True, required=False)
    # Uniqueness is enforced by the view via update_or_create, not the field.
    endpoint = serializers.URLField(max_length=500)

    class Meta:
        model = PushSubscription
        fields = ["id", "endpoint", "keys", "p256dh", "auth", "is_active", "created_at"]
        read_only_fields = ["id", "created_at", "is_active"]
        extra_kwargs = {
            "p256dh": {"write_only": True, "required": False},
            "auth": {"write_only": True, "required": False},
        }

    def create(self, validated_data):
        keys = validated_data.pop("keys", {}) or {}
        validated_data.setdefault("p256dh", keys.get("p256dh", ""))
        validated_data.setdefault("auth", keys.get("auth", ""))
        if not validated_data.get("p256dh") or not validated_data.get("auth"):
            raise serializers.ValidationError("Missing push subscription keys (p256dh/auth).")
        return super().create(validated_data)


class ConsentRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentRecord
        fields = [
            "id", "scope", "granted", "policy_version", "granted_at",
            "revoked_at", "created_at",
        ]
        read_only_fields = ["id", "created_at", "granted_at", "revoked_at"]


class AgentJobSerializer(serializers.ModelSerializer):
    broker_name = serializers.SerializerMethodField()
    broker_email = serializers.SerializerMethodField()
    broker_opt_out_url = serializers.SerializerMethodField()
    exposure_title = serializers.SerializerMethodField()
    exposure_url = serializers.SerializerMethodField()

    class Meta:
        model = AgentJob
        fields = [
            "id", "job_type", "status", "identity", "watchlist", "exposure",
            "campaign", "attempts", "max_attempts", "error_message",
            "claimed_at", "completed_at", "created_at",
            "broker_name", "broker_email", "broker_opt_out_url",
            "exposure_title", "exposure_url",
        ]
        read_only_fields = [
            "id", "status", "attempts", "error_message", "claimed_at",
            "completed_at", "created_at",
        ]

    def get_broker_name(self, obj):
        return obj.campaign.broker.name if obj.campaign and obj.campaign.broker else ""

    def get_broker_email(self, obj):
        return obj.campaign.broker.opt_out_email if obj.campaign and obj.campaign.broker else ""

    def get_broker_opt_out_url(self, obj):
        return obj.campaign.broker.opt_out_url if obj.campaign and obj.campaign.broker else ""

    def get_exposure_title(self, obj):
        return obj.exposure.title if obj.exposure else ""

    def get_exposure_url(self, obj):
        return obj.exposure.url if obj.exposure else ""


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "action", "ip", "user_agent", "metadata", "created_at"]
        read_only_fields = fields


# ===========================================================================
# Households (family plans)
# ===========================================================================
class HouseholdMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True, default="")

    class Meta:
        model = HouseholdMember
        fields = ["id", "user", "username", "display_name", "role", "can_manage", "created_at"]
        read_only_fields = ["id", "created_at"]


class HouseholdSerializer(serializers.ModelSerializer):
    members = HouseholdMemberSerializer(many=True, read_only=True)
    identity_count = serializers.SerializerMethodField()

    class Meta:
        model = Household
        fields = ["id", "name", "owner", "members", "identity_count", "created_at"]
        read_only_fields = ["id", "owner", "created_at"]

    def get_identity_count(self, obj):
        return obj.identities.count()


# ===========================================================================
# Admin
# ===========================================================================
class AdminUserSerializer(serializers.ModelSerializer):
    plan = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField()
    is_active = serializers.BooleanField()
    identity_count = serializers.SerializerMethodField()
    exposure_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "is_staff", "is_superuser", "is_active", "date_joined",
            "plan", "identity_count", "exposure_count",
        ]
        read_only_fields = ["id", "username", "date_joined"]

    def get_plan(self, obj):
        from .entitlements import get_entitlements

        return get_entitlements(obj).plan

    def get_identity_count(self, obj):
        return obj.identities.count()

    def get_exposure_count(self, obj):
        return obj.exposures.count()
