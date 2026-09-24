import uuid

from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    class Plan(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"
        FAMILY = "family", "Family"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    phone = models.CharField(max_length=20, blank=True, default="")
    address = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=50, blank=True, default="")
    zip_code = models.CharField(max_length=10, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile for {self.user.username}"


class BrokerCategory(models.TextChoices):
    PEOPLE_SEARCH = "people_search", "People Search Sites"
    DATA_BROKER = "data_broker", "Data Brokers"
    SOCIAL_MEDIA = "social_media", "Social Media"
    PUBLIC_RECORDS = "public_records", "Public Records"
    MARKETING = "marketing", "Marketing Lists"
    BACKGROUND_CHECK = "background_check", "Background Check"
    OTHER = "other", "Other"


class Broker(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    website_url = models.URLField()
    category = models.CharField(
        max_length=30, choices=BrokerCategory.choices, default=BrokerCategory.OTHER
    )
    description = models.TextField(blank=True, default="")
    opt_out_url = models.URLField(blank=True, default="")
    opt_out_email = models.EmailField(blank=True, default="")
    removal_method = models.CharField(
        max_length=20,
        choices=[
            ("email", "Email Request"),
            ("web_form", "Web Form"),
            ("both", "Email + Web Form"),
            ("manual", "Manual Only"),
        ],
        default="email",
    )
    web_form_config = models.JSONField(
        default=dict, blank=True, help_text="Config for automated form filling"
    )
    email_template = models.TextField(
        blank=True,
        default="",
        help_text="Custom email template. Use {name}, {email}, {address} as placeholders.",
    )
    requires_identity = models.BooleanField(
        default=False, help_text="Whether this broker requires ID verification"
    )
    estimated_days = models.IntegerField(
        default=14, help_text="Estimated days for removal"
    )
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Higher = processed first")
    # Community-sourced compliance signal (0-100): higher = removes data faster.
    compliance_score = models.FloatField(null=True, blank=True)
    removal_rate = models.FloatField(null=True, blank=True, help_text="0-1 fraction removed")
    score_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "name"]

    def __str__(self):
        return self.name


class Scan(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="scans")
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, default="")
    address = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    total_brokers = models.IntegerField(default=0)
    completed_brokers = models.IntegerField(default=0)
    found_count = models.IntegerField(default=0)
    removed_count = models.IntegerField(default=0)
    pending_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    is_recurring = models.BooleanField(default=False)
    recurring_interval_days = models.IntegerField(default=90)
    next_scan_date = models.DateTimeField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Scan {self.id} for {self.full_name}"

    @property
    def progress_percent(self):
        if self.total_brokers == 0:
            return 0
        return int((self.completed_brokers / self.total_brokers) * 100)


class RemovalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        REMOVED = "removed", "Removed"
        FAILED = "failed", "Failed"
        NEEDS_MANUAL = "needs_manual", "Needs Manual Action"
        OPT_OUT_COMPLETE = "opt_out_complete", "Opt-Out Complete"

    class Method(models.TextChoices):
        EMAIL = "email", "Email"
        WEB_FORM = "web_form", "Web Form"
        MANUAL = "manual", "Manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name="requests")
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    method = models.CharField(max_length=20, choices=Method.choices)
    found_url = models.URLField(blank=True, default="")
    removal_url = models.URLField(blank=True, default="")
    confirmation_code = models.CharField(max_length=200, blank=True, default="")
    response_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["scan", "broker"]

    def __str__(self):
        return f"Removal {self.broker.name} for scan {self.scan.id}"


class DataStopRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUBMITTED = "submitted", "Submitted"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="data_stops")
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    stop_selling = models.BooleanField(
        default=True, help_text="Stop selling personal data"
    )
    stop_sharing = models.BooleanField(
        default=True, help_text="Stop sharing with third parties"
    )
    stop_marketing = models.BooleanField(
        default=True, help_text="Stop marketing communications"
    )
    confirmation_code = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "broker"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Data Stop: {self.broker.name} for {self.user.username}"


class ActivityLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Owner of the activity. Scoping every lookup by this field fixes an IDOR
    # where all users' activity was previously readable through the API.
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="activities", null=True, blank=True
    )
    scan = models.ForeignKey(
        Scan, on_delete=models.CASCADE, related_name="activities", null=True, blank=True
    )
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["scan", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.action} at {self.timestamp}"


# ===========================================================================
# Account security
# ===========================================================================
class EmailVerification(models.Model):
    """Email ownership proof. One row per user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_verification")
    token_hash = models.CharField(max_length=64, blank=True, default="")
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"EmailVerification({self.user.username}, verified={self.is_verified})"


class TwoFactorDevice(models.Model):
    """TOTP second factor for a user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="two_factor")
    secret = models.CharField(max_length=64, blank=True, default="")
    is_enabled = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"2FA({self.user.username}, enabled={self.is_enabled})"


class AuditEvent(models.Model):
    """Append-only security audit trail. Rows are immutable at the ORM level."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    action = models.CharField(max_length=100, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self._state.adding is False:
            raise ValueError("AuditEvent rows are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditEvent rows cannot be deleted")

    def __str__(self):
        return f"{self.action} @ {self.created_at}"


class ConsentRecord(models.Model):
    """Explicit, revocable consent for agent capabilities."""

    class Scope(models.TextChoices):
        MONITORING = "monitoring", "Continuous monitoring"
        AUTO_REMOVAL = "auto_removal", "Automatic removal requests"
        DARK_WEB = "dark_web", "Dark-web / breach corpora"
        WEB_SEARCH = "web_search", "Web search indexing"
        LLM = "llm", "AI-assisted drafting"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    scope = models.CharField(max_length=30, choices=Scope.choices)
    granted = models.BooleanField(default=False)
    policy_version = models.CharField(max_length=20, default="1.0")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    granted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "scope"]

    def __str__(self):
        return f"Consent({self.user.username}, {self.scope}={self.granted})"


# ===========================================================================
# Zero-knowledge identity graph
# ===========================================================================
class IdentifierKind(models.TextChoices):
    EMAIL = "email", "Email"
    PHONE = "phone", "Phone"
    FULL_NAME = "full_name", "Full name"
    ADDRESS = "address", "Address"
    USERNAME = "username", "Username"
    DATE_OF_BIRTH = "date_of_birth", "Date of birth"
    SSN = "ssn", "National ID / SSN"
    PASSPORT = "passport", "Passport"
    OTHER = "other", "Other"


class Identity(models.Model):
    """A monitored persona. Contains no plaintext PII."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="identities")
    household = models.ForeignKey(
        "Household", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="identities",
    )
    label = models.CharField(max_length=120, default="Me")
    is_primary = models.BooleanField(default=False)
    is_dependent = models.BooleanField(
        default=False, help_text="A family member / minor monitored by the account owner"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_primary", "label"]
        verbose_name_plural = "identities"

    def __str__(self):
        return f"{self.label} ({self.user.username})"


class Household(models.Model):
    """A family plan grouping multiple accounts and dependents."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_households")
    name = models.CharField(max_length=120, default="My family")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Household({self.name}, owner={self.owner.username})"


class HouseholdMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADULT = "adult", "Adult"
        DEPENDENT = "dependent", "Dependent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="household_memberships"
    )
    display_name = models.CharField(max_length=120, blank=True, default="")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DEPENDENT)
    can_manage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role", "display_name"]
        unique_together = ["household", "user"]

    def __str__(self):
        return f"{self.display_name or (self.user.username if self.user else 'member')} @ {self.household.name}"


class IdentityIdentifier(models.Model):
    """A single identifier, stored as ciphertext + blind index.

    ``value_encrypted`` is ciphertext produced by the client (the server cannot
    read it). ``blind_index`` lets the server match the identifier against
    exposure feeds without decrypting.

    ``role`` distinguishes ordinary identifiers from:
    - ``canary``: a unique tripwire registered with one broker only; if it
      surfaces elsewhere it proves that broker leaked/sold the data.
    - ``alias``: a per-broker throwaway alias (e.g. plus-addressing) used to
      attribute future leaks to the broker that received it.
    """

    class Role(models.TextChoices):
        NORMAL = "normal", "Normal"
        CANARY = "canary", "Canary / tripwire"
        ALIAS = "alias", "Per-broker alias"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identity = models.ForeignKey(
        Identity, on_delete=models.CASCADE, related_name="identifiers"
    )
    kind = models.CharField(max_length=20, choices=IdentifierKind.choices)
    value_encrypted = models.BinaryField(null=True, blank=True)
    blind_index = models.CharField(max_length=64, db_index=True)
    masked_value = models.CharField(max_length=120, blank=True, default="")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.NORMAL)
    linked_broker = models.ForeignKey(
        Broker, on_delete=models.SET_NULL, null=True, blank=True, related_name="linked_identifiers"
    )
    triggered_at = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["identity", "kind", "blind_index"]
        indexes = [models.Index(fields=["blind_index"])]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.masked_value or self.blind_index[:8]}"


# ===========================================================================
# Monitoring / exposure
# ===========================================================================
class Watchlist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="watchlists")
    identity = models.ForeignKey(
        Identity, on_delete=models.CASCADE, related_name="watchlists", null=True, blank=True
    )
    name = models.CharField(max_length=120, default="Default watchlist")
    is_active = models.BooleanField(default=True)
    cadence_hours = models.IntegerField(default=24)
    include_breaches = models.BooleanField(default=True)
    include_web_search = models.BooleanField(default=True)
    include_pastes = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class MonitorRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    watchlist = models.ForeignKey(
        Watchlist, on_delete=models.CASCADE, related_name="runs"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    sources_checked = models.JSONField(default=list, blank=True)
    findings_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"MonitorRun({self.watchlist_id}, {self.status})"


class BreachEvent(models.Model):
    """A breach corpus entry (no per-user PII)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=40)
    breach_name = models.CharField(max_length=200)
    breach_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    data_classes = models.JSONField(default=list, blank=True)
    pwn_count = models.BigIntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["source", "breach_name"]
        ordering = ["-breach_date"]

    def __str__(self):
        return f"{self.breach_name} ({self.source})"


class Exposure(models.Model):
    class Kind(models.TextChoices):
        BREACH = "breach", "Data breach"
        PEOPLE_SEARCH = "people_search", "People-search listing"
        PUBLIC_RECORD = "public_record", "Public record"
        SOCIAL = "social", "Social profile"
        PASTE = "paste", "Paste / leak"
        DARK_WEB = "dark_web", "Dark web"
        SEARCH_RESULT = "search_result", "Search result"
        CANARY = "canary", "Canary triggered (proven leak)"
        OTHER = "other", "Other"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        NEW = "new", "New"
        TRIAGED = "triaged", "Triaged"
        REMOVAL_QUEUED = "removal_queued", "Removal queued"
        REMOVAL_SENT = "removal_sent", "Removal sent"
        REMOVED = "removed", "Removed"
        VERIFIED = "verified", "Removed & verified"
        REAPPEARED = "reappeared", "Reappeared"
        DISMISSED = "dismissed", "Dismissed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exposures")
    identity = models.ForeignKey(
        Identity, on_delete=models.SET_NULL, null=True, blank=True, related_name="exposures"
    )
    watchlist = models.ForeignKey(
        Watchlist, on_delete=models.SET_NULL, null=True, blank=True, related_name="exposures"
    )
    monitor_run = models.ForeignKey(
        MonitorRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="exposures"
    )
    breach_event = models.ForeignKey(
        BreachEvent, on_delete=models.SET_NULL, null=True, blank=True, related_name="exposures"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.MEDIUM
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    title = models.CharField(max_length=300)
    source = models.CharField(max_length=40, blank=True, default="")
    url = models.URLField(max_length=500, blank=True, default="")
    site_domain = models.CharField(max_length=200, blank=True, default="")
    matched_blind_index = models.CharField(max_length=64, blank=True, default="", db_index=True)
    matched_identifier_kind = models.CharField(max_length=20, blank=True, default="")
    masked_evidence = models.CharField(max_length=300, blank=True, default="")
    confidence = models.FloatField(default=0.5)
    fingerprint = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # Correlated provenance: which broker likely leaked/sold this record.
    provenance = models.JSONField(default=dict, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-severity", "-last_seen"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "-last_seen"]),
        ]

    def __str__(self):
        return f"Exposure({self.kind}, {self.severity}, {self.title[:40]})"


# ===========================================================================
# Removal campaigns / evidence
# ===========================================================================
class RemovalCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUBMITTED = "submitted", "Submitted"
        AWAITING_RESPONSE = "awaiting_response", "Awaiting response"
        REMOVED = "removed", "Removed"
        VERIFIED = "verified", "Verified"
        ESCALATED = "escalated", "Escalated to regulator"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WEB_FORM = "web_form", "Web form"
        MANUAL = "manual", "Manual"
        REGULATOR = "regulator", "Regulator complaint"
        DEINDEX = "deindex", "Search-engine de-index"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="removal_campaigns")
    exposure = models.ForeignKey(
        Exposure, on_delete=models.CASCADE, related_name="campaigns", null=True, blank=True
    )
    broker = models.ForeignKey(
        Broker, on_delete=models.SET_NULL, null=True, blank=True, related_name="campaigns"
    )
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.EMAIL)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    jurisdiction = models.CharField(max_length=40, blank=True, default="")
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    confirmation_code = models.CharField(max_length=200, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    requested_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Campaign({self.channel}, {self.status}, exposure={self.exposure_id})"


class RemovalEvidence(models.Model):
    """Hash-addressed, optionally encrypted proof attached to a campaign."""

    class Kind(models.TextChoices):
        EMAIL_RECEIPT = "email_receipt", "Email receipt"
        SCREENSHOT = "screenshot", "Screenshot"
        RESPONSE = "response", "Broker response"
        CONFIRMATION = "confirmation", "Confirmation"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        RemovalCampaign, on_delete=models.CASCADE, related_name="evidence"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    ciphertext = models.BinaryField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    # Hash-chained, tamper-evident receipt (per campaign).
    sequence = models.IntegerField(default=0)
    prev_hash = models.CharField(max_length=64, blank=True, default="")
    entry_hash = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence", "created_at"]
        unique_together = ["campaign", "sequence"]

    def __str__(self):
        return f"Evidence({self.kind}, {self.sha256[:10]})"


# ===========================================================================
# Notifications
# ===========================================================================
class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    severity = models.CharField(
        max_length=20, choices=Exposure.Severity.choices, default=Exposure.Severity.MEDIUM
    )
    exposure = models.ForeignKey(
        Exposure, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications"
    )
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification({self.title[:40]})"


class NotificationChannelConfig(models.Model):
    class Kind(models.TextChoices):
        EMAIL = "email", "Email"
        WEBHOOK = "webhook", "Webhook"
        TELEGRAM = "telegram", "Telegram"
        SLACK = "slack", "Slack"
        DISCORD = "discord", "Discord"
        SIGNAL = "signal", "Signal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notification_channels"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.EMAIL)
    target = models.CharField(
        max_length=500,
        help_text="Destination address/URL, encrypted at rest with FIELD_ENCRYPTION_KEY",
    )
    is_active = models.BooleanField(default=True)
    severity_threshold = models.CharField(
        max_length=20, choices=Exposure.Severity.choices, default=Exposure.Severity.MEDIUM
    )
    signing_secret = models.BinaryField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"NotifyChannel({self.kind})"


class PushSubscription(models.Model):
    """A browser Web Push (VAPID) subscription for a user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PushSubscription({self.user.username}, {self.endpoint[:40]})"

    def as_info(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }


# ===========================================================================
# On-device executor job queue
# ===========================================================================
class AgentJob(models.Model):
    """A unit of work handed to the user's on-device agent.

    Payloads and results are ciphertext: the server never sees plaintext PII and
    only relays opaque blobs to the trusted device that holds the vault key.
    """

    class Type(models.TextChoices):
        MONITOR = "monitor", "Run monitoring"
        SEND_EMAIL = "send_email", "Send removal email"
        FILL_WEB_FORM = "fill_web_form", "Fill removal web form"
        VERIFY = "verify", "Verify removal"
        ESCALATE = "escalate", "Escalate to regulator"
        DEINDEX = "deindex", "Request search-engine de-index"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        CLAIMED = "claimed", "Claimed"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="agent_jobs")
    identity = models.ForeignKey(
        Identity, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_jobs"
    )
    watchlist = models.ForeignKey(
        Watchlist, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_jobs"
    )
    exposure = models.ForeignKey(
        Exposure, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_jobs"
    )
    campaign = models.ForeignKey(
        RemovalCampaign, on_delete=models.CASCADE, null=True, blank=True, related_name="agent_jobs"
    )
    job_type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    payload_encrypted = models.BinaryField(null=True, blank=True)
    result_encrypted = models.BinaryField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    error_message = models.TextField(blank=True, default="")
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"AgentJob({self.job_type}, {self.status})"
