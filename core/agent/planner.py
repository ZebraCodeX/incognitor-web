"""Removal planning: choose jurisdiction, channel and deadline for an exposure."""


from django.conf import settings
from django.utils import timezone

from core.services.legal import select_jurisdiction


def choose_jurisdiction(identifiers: dict) -> str:
    return select_jurisdiction(identifiers or {})


def choose_channel(broker) -> str:
    """Pick the best removal channel for a broker."""
    if broker is None:
        return "manual"
    if broker.removal_method in {"email", "both"} and broker.opt_out_email:
        return "email"
    if broker.removal_method in {"web_form", "both"} and broker.web_form_config:
        return "web_form"
    return "manual"


def deadline_from_now(days=None):
    days = days or getattr(settings, "SENTINEL_REMOVAL_DEADLINE_DAYS", 30)
    return timezone.now() + timezone.timedelta(days=days)


def plan_campaign(exposure, broker, identifiers: dict) -> dict:
    """Return the plan for turning an exposure into a removal campaign."""
    return {
        "channel": choose_channel(broker),
        "jurisdiction": choose_jurisdiction(identifiers),
        "deadline_at": deadline_from_now(),
    }
