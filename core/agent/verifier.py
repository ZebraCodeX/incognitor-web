"""Campaign verification and escalation logic."""


from django.conf import settings
from django.utils import timezone


def is_overdue(campaign, now=None) -> bool:
    now = now or timezone.now()
    if campaign.deadline_at and campaign.deadline_at < now:
        return campaign.status in {
            "submitted",
            "awaiting_response",
            "running",
            "queued",
        }
    return False


def needs_verification(campaign, now=None) -> bool:
    """A submitted campaign is re-checked after the verify interval."""
    now = now or timezone.now()
    interval = getattr(settings, "SENTINEL_VERIFY_INTERVAL_DAYS", 7)
    if campaign.status not in {"submitted", "awaiting_response", "removed"}:
        return False
    anchor = campaign.submitted_at or campaign.completed_at or campaign.created_at
    if anchor is None:
        return False
    return (now - anchor) >= timezone.timedelta(days=interval)


def next_action(campaign, now=None) -> str:
    """Return one of: ``escalate``, ``verify``, ``retry``, ``none``."""
    now = now or timezone.now()
    if campaign.status in {"verified", "cancelled", "escalated"}:
        return "none"
    if is_overdue(campaign, now):
        return "escalate"
    if needs_verification(campaign, now):
        return "verify"
    if campaign.status == "failed" and campaign.attempts < campaign.max_attempts:
        return "retry"
    return "none"
