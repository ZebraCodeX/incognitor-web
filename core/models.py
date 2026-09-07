from django.db import models
from django.contrib.auth.models import User
import uuid


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
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
    scan = models.ForeignKey(
        Scan, on_delete=models.CASCADE, related_name="activities", null=True, blank=True
    )
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.action} at {self.timestamp}"
