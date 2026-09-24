from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Count
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .agent import SentinelAgent, triage
from .agent.base import Finding
from .audit import record as audit_record
from .crypto import blind_index
from .entitlements import get_entitlements
from .models import (
    ActivityLog,
    AgentJob,
    AuditEvent,
    Broker,
    ConsentRecord,
    DataStopRequest,
    EmailVerification,
    Exposure,
    Household,
    HouseholdMember,
    Identity,
    MonitorRun,
    Notification,
    NotificationChannelConfig,
    PushSubscription,
    RemovalCampaign,
    Scan,
    TwoFactorDevice,
    UserProfile,
    Watchlist,
)
from .runner import start_scan_in_thread
from .serializers import (
    ActivityLogSerializer,
    AdminUserSerializer,
    AgentJobSerializer,
    AuditEventSerializer,
    BrokerSerializer,
    ConsentRecordSerializer,
    DataStopRequestSerializer,
    ExposureSerializer,
    HouseholdMemberSerializer,
    HouseholdSerializer,
    IdentitySerializer,
    NotificationChannelConfigSerializer,
    NotificationSerializer,
    PushSubscriptionSerializer,
    RemovalCampaignSerializer,
    RemovalRequestSerializer,
    ScanSerializer,
    UserProfileSerializer,
    UserSerializer,
    WatchlistSerializer,
)
from .services import aliases
from .services import provenance as provenance_service
from .services.ledger import append as ledger_append
from .services.ledger import verify_chain
from .services.scan_engine import ScanEngine
from .throttling import AgentRateThrottle, LoginRateThrottle, SignupRateThrottle


def _harden_session(request):
    request.session.set_expiry(60 * 60 * 12)
    request.session.cycle_key()


class AuthViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def get_throttles(self):
        if self.action == "login":
            return [LoginRateThrottle()]
        if self.action == "signup":
            return [SignupRateThrottle()]
        return []

    @action(detail=False, methods=["post"])
    def login(self, request):
        username = request.data.get("username") or request.data.get("email")
        password = request.data.get("password")
        otp = request.data.get("otp", "")

        lock_key = f"login_fail:{self._client_ip(request)}:{username}"
        failures = cache.get(lock_key, 0)
        if failures >= settings.LOGIN_MAX_ATTEMPTS:
            audit_record("auth.login.locked", username=username)
            return Response(
                {"error": "Too many failed attempts. Try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            cache.set(lock_key, failures + 1, settings.LOGIN_LOCKOUT_SECONDS)
            audit_record("auth.login.failed", username=username)
            return Response({"error": "Invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)

        device = getattr(user, "two_factor", None)
        if device and device.is_enabled:
            import pyotp

            if not otp or not pyotp.TOTP(device.secret).verify(otp, valid_window=1):
                return Response(
                    {"error": "Two-factor code required or invalid", "mfa_required": True},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            device.last_used_at = timezone.now()
            device.save(update_fields=["last_used_at"])

        if settings.REQUIRE_EMAIL_VERIFICATION:
            verification = getattr(user, "email_verification", None)
            if verification and not verification.is_verified:
                return Response(
                    {"error": "Email address not verified", "email_unverified": True},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        login(request, user)
        _harden_session(request)
        cache.delete(lock_key)
        audit_record("auth.login.success", user=user, request=request)
        return Response(UserSerializer(user).data)

    @action(detail=False, methods=["post"])
    def signup(self, request):
        data = request.data
        username = data.get("username")
        email = data.get("email")
        password = data.get("password1")
        password2 = data.get("password2")

        if not username or not email or not password:
            return Response({"error": "Username, email, and password are required"}, status=400)
        if password != password2:
            return Response({"error": "Passwords do not match"}, status=400)
        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already taken"}, status=400)
        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already registered"}, status=400)

        # Enforce Django's configured password validators (the old code bypassed
        # them by calling create_user directly).
        try:
            validate_password(password, User(username=username, email=email))
        except ValidationError as exc:
            return Response({"error": " ".join(exc.messages)}, status=400)

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
            )
            UserProfile.objects.create(user=user)
            email_verification = EmailVerification.objects.create(user=user)
        self._send_verification_email(request, user, email_verification)
        login(request, user)
        _harden_session(request)
        audit_record("auth.signup", user=user, request=request)
        return Response(UserSerializer(user).data, status=201)

    @action(detail=False, methods=["post"])
    def logout(self, request):
        audit_record("auth.logout", user=request.user if request.user.is_authenticated else None)
        logout(request)
        return Response({"status": "ok"})

    # -- email verification -------------------------------------------------
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def request_email_verification(self, request):
        verification, _ = EmailVerification.objects.get_or_create(user=request.user)
        self._send_verification_email(request, request.user, verification)
        return Response({"status": "sent"})

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def verify_email(self, request):
        token = request.data.get("token", "")
        import hashlib

        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        verification = getattr(request.user, "email_verification", None)
        if not verification or not verification.token_hash:
            return Response({"error": "No verification pending"}, status=400)
        if not hmac_compare(verification.token_hash, digest):
            return Response({"error": "Invalid token"}, status=400)
        verification.is_verified = True
        verification.verified_at = timezone.now()
        verification.token_hash = ""
        verification.save(update_fields=["is_verified", "verified_at", "token_hash"])
        audit_record("auth.email.verified", user=request.user)
        return Response({"status": "verified"})

    # -- TOTP MFA -----------------------------------------------------------
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def mfa_setup(self, request):
        import pyotp

        device, _ = TwoFactorDevice.objects.get_or_create(user=request.user)
        if device.is_enabled:
            return Response({"error": "MFA already enabled"}, status=400)
        device.secret = pyotp.random_base32()
        device.save(update_fields=["secret"])
        uri = pyotp.totp.TOTP(device.secret).provisioning_uri(
            name=request.user.email or request.user.username,
            issuer_name="Incognitor",
        )
        return Response({"secret": device.secret, "otpauth_url": uri})

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def mfa_confirm(self, request):
        import pyotp

        code = request.data.get("code", "")
        device = getattr(request.user, "two_factor", None)
        if not device or not device.secret:
            return Response({"error": "Start MFA setup first"}, status=400)
        if not pyotp.TOTP(device.secret).verify(code, valid_window=1):
            return Response({"error": "Invalid code"}, status=400)
        device.is_enabled = True
        device.confirmed_at = timezone.now()
        device.save(update_fields=["is_enabled", "confirmed_at"])
        audit_record("auth.mfa.enabled", user=request.user)
        return Response({"status": "enabled"})

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def mfa_disable(self, request):
        import pyotp

        code = request.data.get("code", "")
        device = getattr(request.user, "two_factor", None)
        if not device or not device.is_enabled:
            return Response({"error": "MFA not enabled"}, status=400)
        if not pyotp.TOTP(device.secret).verify(code, valid_window=1):
            return Response({"error": "Invalid code"}, status=400)
        device.is_enabled = False
        device.secret = ""
        device.save(update_fields=["is_enabled", "secret"])
        audit_record("auth.mfa.disabled", user=request.user)
        return Response({"status": "disabled"})

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        return Response(UserSerializer(request.user).data)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _client_ip(request):
        from .audit import client_ip

        return client_ip(request)

    @staticmethod
    def _send_verification_email(request, user, verification):
        import hashlib
        import secrets

        token = secrets.token_urlsafe(32)
        verification.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        verification.save(update_fields=["token_hash"])
        link = request.build_absolute_uri(f"/verify-email/?token={token}")
        try:
            EmailMessage(
                subject="Verify your Incognitor email",
                body=f"Hi {user.username},\n\nConfirm your email address:\n{link}\n",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            ).send()
        except Exception:  # noqa: BLE001
            pass


def hmac_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a or "", b or "")


class BrokerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Broker.objects.filter(is_active=True)
    serializer_class = BrokerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs


class ScanViewSet(viewsets.ModelViewSet):
    serializer_class = ScanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Scan.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        scan = serializer.save(user=self.request.user)
        start_scan_in_thread(scan)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        scan = self.get_object()
        if scan.status in [Scan.Status.RUNNING, Scan.Status.COMPLETED]:
            return Response({"error": f"Scan already {scan.status}"}, status=400)
        start_scan_in_thread(scan)
        return Response({"status": "started", "mode": "thread"})

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        scan = self.get_object()
        by_status = scan.requests.values("status").annotate(count=Count("id"))
        status_map = {s["status"]: s["count"] for s in by_status}
        return Response({
            "id": str(scan.id),
            "status": scan.status,
            "progress_percent": scan.progress_percent,
            "total_brokers": scan.total_brokers,
            "completed_brokers": scan.completed_brokers,
            "removed_count": scan.removed_count,
            "found_count": scan.found_count,
            "failed_count": scan.failed_count,
            "by_status": status_map,
            "error_message": scan.error_message,
            "requests": RemovalRequestSerializer(
                scan.requests.select_related("broker").all(), many=True
            ).data,
        })


class DataStopViewSet(viewsets.ModelViewSet):
    serializer_class = DataStopRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DataStopRequest.objects.filter(user=self.request.user).select_related("broker")

    def perform_create(self, serializer):
        broker = get_object_or_404(Broker, id=self.request.data.get("broker_id"))
        try:
            result = ScanEngine.submit_data_stop_request(
                self.request.user,
                broker,
                stop_selling=serializer.validated_data.get("stop_selling", True),
                stop_sharing=serializer.validated_data.get("stop_sharing", True),
                stop_marketing=serializer.validated_data.get("stop_marketing", True),
            )
            return Response(DataStopRequestSerializer(result).data, status=201)
        except Exception as e:
            serializer.save(
                user=self.request.user,
                broker=broker,
                status=DataStopRequest.Status.FAILED,
                notes=str(e),
            )

    @action(detail=False, methods=["post"])
    def bulk_submit(self, request):
        broker_ids = request.data.get("broker_ids", [])
        stop_selling = request.data.get("stop_selling", True)
        stop_sharing = request.data.get("stop_sharing", True)
        stop_marketing = request.data.get("stop_marketing", True)

        results = []
        for bid in broker_ids:
            broker = get_object_or_404(Broker, id=bid)
            try:
                ScanEngine.submit_data_stop_request(
                    request.user, broker,
                    stop_selling=stop_selling,
                    stop_sharing=stop_sharing,
                    stop_marketing=stop_marketing,
                )
                results.append({"broker": broker.name, "status": "submitted"})
            except Exception as e:
                results.append({"broker": broker.name, "status": "failed", "error": str(e)})

        return Response({"results": results})


class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ActivityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # SECURITY: scope to the requesting user only. Previously this returned
        # ActivityLog.objects.all(), leaking every user's activity.
        from django.db.models import Q

        qs = ActivityLog.objects.filter(
            Q(user=self.request.user) | Q(scan__user=self.request.user)
        )
        scan_id = self.request.query_params.get("scan")
        if scan_id:
            qs = qs.filter(scan_id=scan_id)
        return qs[:50]


# ===========================================================================
# Sentinel viewsets
# ===========================================================================
class IdentityViewSet(viewsets.ModelViewSet):
    serializer_class = IdentitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Identity.objects.filter(user=self.request.user).prefetch_related("identifiers")

    def create(self, request, *args, **kwargs):
        ent = get_entitlements(request.user)
        count = Identity.objects.filter(user=request.user).count()
        if not ent.within_identity_limit(count):
            return Response(
                {"error": f"Your plan allows up to {ent.max_identities} identities."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def canary(self, request, pk=None):
        """Create a canary/tripwire identifier for one broker.

        Accepts ``base_email`` (or ``base_value``) + ``broker_id`` and
        ``kind`` (default email). The plaintext is used only to compute the
        blind index and is not stored.
        """
        identity = self.get_object()
        broker = get_object_or_404(Broker, id=request.data.get("broker_id"))
        base = request.data.get("base_email") or request.data.get("base_value")
        kind = request.data.get("kind", "email")
        if not base:
            return Response({"error": "base_email is required"}, status=400)
        identifier, value = aliases.create_canary(identity, broker, base, kind)
        audit_record("sentinel.canary.created", user=request.user, broker=broker.name)
        return Response(
            {
                "id": str(identifier.id),
                "broker": broker.name,
                "kind": kind,
                "value": value,
                "masked_value": identifier.masked_value,
            },
            status=201,
        )

    @action(detail=True, methods=["post"])
    def alias(self, request, pk=None):
        """Create a per-broker alias identity (for leak attribution)."""
        identity = self.get_object()
        broker = get_object_or_404(Broker, id=request.data.get("broker_id"))
        base = request.data.get("base_email") or request.data.get("base_value")
        kind = request.data.get("kind", "email")
        if not base:
            return Response({"error": "base_email is required"}, status=400)
        identifier, value = aliases.create_alias(identity, broker, base, kind)
        audit_record("sentinel.alias.created", user=request.user, broker=broker.name)
        return Response(
            {"id": str(identifier.id), "broker": broker.name, "kind": kind,
             "value": value, "masked_value": identifier.masked_value},
            status=201,
        )


class WatchlistViewSet(viewsets.ModelViewSet):
    serializer_class = WatchlistSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Watchlist.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ExposureViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ExposureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Exposure.objects.filter(user=self.request.user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        severity = self.request.query_params.get("severity")
        if severity:
            qs = qs.filter(severity=severity)
        return qs

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        exposure = self.get_object()
        exposure.status = Exposure.Status.DISMISSED
        exposure.save(update_fields=["status"])
        audit_record("sentinel.exposure.dismissed", user=request.user, exposure=str(exposure.id))
        return Response({"status": "dismissed"})

    @action(detail=True, methods=["post"])
    def request_removal(self, request, pk=None):
        exposure = self.get_object()
        campaign = SentinelAgent(request.user).queue_removal(exposure)
        return Response(RemovalCampaignSerializer(campaign).data, status=201)

    @action(detail=True, methods=["get"])
    def provenance(self, request, pk=None):
        """Return (and refresh) the likely source broker for an exposure."""
        exposure = self.get_object()
        data = provenance_service.refresh_exposure(exposure)
        return Response(data)


class RemovalCampaignViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RemovalCampaignSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RemovalCampaign.objects.filter(user=self.request.user).select_related(
            "broker", "exposure"
        )

    @action(detail=True, methods=["get"])
    def verify_ledger(self, request, pk=None):
        campaign = self.get_object()
        return Response(verify_chain(campaign))


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response({"status": "read"})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"status": "read"})

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def stream(self, request):
        """Server-Sent Events stream of new notifications."""
        last_seen = timezone.now()

        def event_stream():
            nonlocal last_seen
            import json
            import time

            while True:
                new = Notification.objects.filter(
                    user=request.user, created_at__gt=last_seen
                ).order_by("created_at")
                for notification in new:
                    last_seen = notification.created_at
                    payload = NotificationSerializer(notification).data
                    yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(5)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class NotificationChannelConfigViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationChannelConfigSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NotificationChannelConfig.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PushViewSet(viewsets.ViewSet):
    """Web Push (VAPID) subscription management."""

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def vapid_public_key(self, request):
        from .services import push

        return Response(
            {"public_key": push.public_key(), "enabled": push.is_configured()}
        )

    @action(detail=False, methods=["post"])
    def subscribe(self, request):
        serializer = PushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        keys = data.get("keys", {}) or {}
        p256dh = data.get("p256dh") or keys.get("p256dh")
        auth = data.get("auth") or keys.get("auth")
        if not p256dh or not auth:
            return Response(
                {"error": "Missing push subscription keys (p256dh/auth)."}, status=400
            )
        subscription, created = PushSubscription.objects.update_or_create(
            endpoint=data["endpoint"],
            defaults={
                "user": request.user,
                "p256dh": p256dh,
                "auth": auth,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:512],
                "is_active": True,
            },
        )
        audit_record("sentinel.push.subscribe", user=request.user, created=created)
        return Response({"status": "subscribed"}, status=201 if created else 200)

    @action(detail=False, methods=["post"])
    def unsubscribe(self, request):
        endpoint = request.data.get("endpoint", "")
        updated = PushSubscription.objects.filter(
            user=request.user, endpoint=endpoint
        ).update(is_active=False)
        audit_record("sentinel.push.unsubscribe", user=request.user, found=updated)
        return Response({"status": "unsubscribed", "found": updated})

    @action(detail=False, methods=["post"])
    def test(self, request):
        from .services import push

        sent = push.send_push(
            request.user, "Incognitor test notification",
            "Web Push is working.", {"url": "/exposures/"},
        )
        return Response({"sent": sent, "enabled": push.is_configured()})


class ConsentViewSet(viewsets.ModelViewSet):
    serializer_class = ConsentRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ConsentRecord.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AgentJobViewSet(viewsets.ReadOnlyModelViewSet):
    """Queue endpoint used by the on-device executor."""

    serializer_class = AgentJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = AgentJob.objects.filter(user=self.request.user)
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        job = self.get_object()
        if job.status not in [AgentJob.Status.QUEUED, AgentJob.Status.FAILED]:
            return Response({"error": f"Job is {job.status}"}, status=400)
        job.status = AgentJob.Status.CLAIMED
        job.claimed_at = timezone.now()
        job.attempts += 1
        job.save(update_fields=["status", "claimed_at", "attempts"])
        return Response(AgentJobSerializer(job).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        job = self.get_object()
        job.status = AgentJob.Status.COMPLETED
        job.completed_at = timezone.now()
        if request.data.get("result_ciphertext"):
            job.result_encrypted = request.data["result_ciphertext"].encode("utf-8")
        if request.data.get("confirmation_code"):
            job.error_message = ""
        job.save(update_fields=["status", "completed_at", "result_encrypted", "error_message"])

        if job.campaign:
            campaign = job.campaign
            ledger_append(
                campaign,
                "job_completed",
                {
                    "job_type": job.job_type,
                    "confirmation": str(request.data.get("confirmation_code", ""))[:200],
                },
                ciphertext=job.result_encrypted,
            )
            # De-index jobs are auxiliary and do not mark the broker opt-out as
            # submitted.
            if job.job_type != AgentJob.Type.DEINDEX:
                campaign.status = RemovalCampaign.Status.SUBMITTED
                campaign.submitted_at = timezone.now()
                if request.data.get("confirmation_code"):
                    campaign.confirmation_code = request.data["confirmation_code"][:200]
                campaign.save(update_fields=["status", "submitted_at", "confirmation_code"])
                if campaign.exposure:
                    campaign.exposure.status = Exposure.Status.REMOVAL_SENT
                    campaign.exposure.save(update_fields=["status"])
        audit_record("sentinel.job.completed", user=request.user, job=str(job.id))
        return Response(AgentJobSerializer(job).data)

    @action(detail=True, methods=["post"])
    def fail(self, request, pk=None):
        job = self.get_object()
        job.status = AgentJob.Status.FAILED
        job.error_message = str(request.data.get("error", ""))[:2000]
        job.save(update_fields=["status", "error_message"])
        audit_record("sentinel.job.failed", user=request.user, job=str(job.id))
        return Response(AgentJobSerializer(job).data)


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AuditEvent.objects.filter(user=self.request.user)[:200]


class AgentViewSet(viewsets.ViewSet):
    """Trigger points for the Sentinel agent."""

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        return [AgentRateThrottle()]

    @action(detail=False, methods=["post"])
    def run(self, request):
        """Run a monitoring pass.

        ``identifiers`` are supplied transiently by the on-device agent and are
        never stored (only blind indexes are persisted).
        """
        identifiers = request.data.get("identifiers") or {}
        if not isinstance(identifiers, dict):
            return Response({"error": "identifiers must be an object"}, status=400)

        watchlist_id = request.data.get("watchlist_id")
        if watchlist_id:
            watchlist = get_object_or_404(Watchlist, id=watchlist_id, user=request.user)
        else:
            watchlist, _ = Watchlist.objects.get_or_create(
                user=request.user, name="Default watchlist"
            )

        ent = get_entitlements(request.user)
        requested = request.data.get("auto_remove")
        if requested is None:
            allow_auto_remove = ent.auto_remove
        else:
            allow_auto_remove = bool(requested) and (ent.auto_remove or request.user.is_staff)

        run, created = SentinelAgent(request.user).run_watchlist(
            watchlist,
            identifiers=identifiers,
            allow_auto_remove=allow_auto_remove,
        )
        audit_record(
            "sentinel.agent.run",
            user=request.user,
            watchlist=str(watchlist.id),
            findings=run.findings_count,
        )
        return Response({
            "run_id": str(run.id),
            "status": run.status,
            "findings": run.findings_count,
            "new_exposures": ExposureSerializer(created, many=True).data,
            "sources_checked": run.sources_checked,
        })

    @action(detail=False, methods=["post"])
    def handle_on_device_finding(self, request):
        """Receive a finding discovered locally by the on-device agent.

        The client sends the identifier's blind index (never the value) plus the
        finding metadata; the server records it without seeing PII.
        """
        kind = request.data.get("kind", "other")
        identifier_kind = request.data.get("identifier_kind", "")
        blind = request.data.get("blind_index", "")
        if not blind and request.data.get("value"):
            blind = blind_index(identifier_kind, request.data["value"])

        payload = {
            "source": request.data.get("source", "on_device"),
            "kind": kind,
            "title": request.data.get("title", "On-device finding"),
            "url": request.data.get("url", ""),
            "matched_kind": identifier_kind,
            "matched_value": "",
            "masked_evidence": request.data.get("masked_evidence", ""),
            "confidence": float(request.data.get("confidence", 0.8)),
            "data_classes": request.data.get("data_classes", []),
            "metadata": {"blind_index": blind, "on_device": True},
        }

        finding = Finding(**payload)
        finding.severity = request.data.get("severity") or triage.score_severity(finding)
        watchlist, _ = Watchlist.objects.get_or_create(
            user=request.user, name="Default watchlist"
        )
        run = MonitorRun.objects.create(
            watchlist=watchlist, status=MonitorRun.Status.RUNNING, started_at=timezone.now()
        )
        exposure, created = SentinelAgent(request.user)._persist_finding(
            finding, watchlist, run
        )
        run.status = MonitorRun.Status.COMPLETED
        run.findings_count = 1
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "findings_count", "completed_at"])
        if created:
            agent = SentinelAgent(request.user)
            agent.alert(exposure)
            if request.data.get("auto_remove", True):
                agent.queue_removal(exposure)
        audit_record("sentinel.on_device.finding", user=request.user, created=created)
        return Response(
            {"id": str(exposure.id), "created": created}, status=201 if created else 200
        )


# ===========================================================================
# Households (family plans)
# ===========================================================================
class HouseholdViewSet(viewsets.ModelViewSet):
    serializer_class = HouseholdSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from django.db.models import Q

        return Household.objects.filter(
            Q(owner=self.request.user) | Q(members__user=self.request.user)
        ).distinct().prefetch_related("members")

    def perform_create(self, serializer):
        household = serializer.save(owner=self.request.user)
        HouseholdMember.objects.create(
            household=household, user=self.request.user,
            role=HouseholdMember.Role.OWNER, can_manage=True,
        )

    def _household(self, pk):
        return get_object_or_404(Household, id=pk, owner=self.request.user)

    @action(detail=True, methods=["post"])
    def add_member(self, request, pk=None):
        household = self._household(pk)
        ent = get_entitlements(request.user)
        current = household.members.exclude(role=HouseholdMember.Role.OWNER).count()
        if ent.max_family_members != -1 and current >= ent.max_family_members:
            return Response(
                {"error": f"Your plan allows {ent.max_family_members} family members."},
                status=status.HTTP_403_FORBIDDEN,
            )
        user_id = request.data.get("user_id")
        member_user = get_object_or_404(User, id=user_id) if user_id else None
        member = HouseholdMember.objects.create(
            household=household,
            user=member_user,
            display_name=request.data.get("display_name", ""),
            role=request.data.get("role", HouseholdMember.Role.DEPENDENT),
            can_manage=bool(request.data.get("can_manage", False)),
        )
        audit_record("sentinel.household.member_added", user=request.user,
                     household=str(household.id))
        return Response(HouseholdMemberSerializer(member).data, status=201)

    @action(detail=True, methods=["post"])
    def add_dependent(self, request, pk=None):
        """Create a dependent Identity (e.g. a minor) owned by the account."""
        household = self._household(pk)
        ent = get_entitlements(request.user)
        count = Identity.objects.filter(user=request.user).count()
        if not ent.within_identity_limit(count):
            return Response(
                {"error": f"Your plan allows up to {ent.max_identities} identities."},
                status=status.HTTP_403_FORBIDDEN,
            )
        label = request.data.get("label", "Dependent")
        identity = Identity.objects.create(
            user=request.user, household=household, label=label, is_dependent=True
        )
        HouseholdMember.objects.create(
            household=household, display_name=label,
            role=HouseholdMember.Role.DEPENDENT,
        )
        return Response(IdentitySerializer(identity).data, status=201)


class HouseholdMemberViewSet(viewsets.ModelViewSet):
    serializer_class = HouseholdMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return HouseholdMember.objects.filter(
            household__owner=self.request.user
        ).select_related("user")

    def perform_create(self, serializer):
        household = get_object_or_404(
            Household, id=self.request.data.get("household"), owner=self.request.user
        )
        serializer.save(household=household)


# ===========================================================================
# Admin / operator oversight (staff only)
# ===========================================================================
class AdminOverviewView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count

        exposure_by_severity = {
            row["severity"]: row["count"]
            for row in Exposure.objects.values("severity").annotate(count=Count("id"))
        }
        campaign_by_status = {
            row["status"]: row["count"]
            for row in RemovalCampaign.objects.values("status").annotate(count=Count("id"))
        }
        return Response({
            "users": User.objects.count(),
            "staff": User.objects.filter(is_staff=True).count(),
            "identities": Identity.objects.count(),
            "exposures": Exposure.objects.count(),
            "exposures_by_severity": exposure_by_severity,
            "campaigns": RemovalCampaign.objects.count(),
            "campaigns_by_status": campaign_by_status,
            "agent_jobs": AgentJob.objects.count(),
            "queued_jobs": AgentJob.objects.filter(status="queued").count(),
            "brokers": Broker.objects.count(),
            "notifications": Notification.objects.count(),
        })


class AdminUserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    queryset = User.objects.all().order_by("-date_joined")

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(username__icontains=q) | qs.filter(email__icontains=q)
        return qs

    @action(detail=True, methods=["post"])
    def set_plan(self, request, pk=None):
        user = self.get_object()
        plan = request.data.get("plan")
        if plan not in dict(UserProfile.Plan.choices):
            return Response({"error": "invalid plan"}, status=400)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.plan = plan
        profile.save(update_fields=["plan"])
        audit_record("admin.user.set_plan", user=request.user, target=user.username, plan=plan)
        return Response(AdminUserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def set_staff(self, request, pk=None):
        user = self.get_object()
        is_staff = bool(request.data.get("is_staff", False))
        user.is_staff = is_staff
        user.save(update_fields=["is_staff"])
        audit_record("admin.user.set_staff", user=request.user, target=user.username,
                     is_staff=is_staff)
        return Response(AdminUserSerializer(user).data)


class AdminExposureViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ExposureSerializer
    permission_classes = [IsAdminUser]
    queryset = Exposure.objects.all().select_related("user", "breach_event")


class AdminCampaignViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RemovalCampaignSerializer
    permission_classes = [IsAdminUser]
    queryset = RemovalCampaign.objects.all().select_related("user", "broker", "exposure")


class AdminBrokerViewSet(viewsets.ModelViewSet):
    serializer_class = BrokerSerializer
    permission_classes = [IsAdminUser]
    queryset = Broker.objects.all()

    @action(detail=True, methods=["post"])
    def set_active(self, request, pk=None):
        broker = self.get_object()
        broker.is_active = bool(request.data.get("is_active", True))
        broker.save(update_fields=["is_active"])
        audit_record("admin.broker.set_active", user=request.user, broker=broker.name,
                     is_active=broker.is_active)
        return Response(BrokerSerializer(broker).data)
