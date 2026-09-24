"""Append-only audit trail.

Every security-relevant action (login, signup, scan start, removal send, agent
run, 2FA change, ...) is recorded with actor, IP, user-agent and metadata. The
model refuses updates/deletes so the trail is tamper-evident at the ORM level.
"""

import logging

from .middleware import get_current_request

logger = logging.getLogger(__name__)


def client_ip(request):
    """Return the originating client IP, honouring a single proxy hop."""
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record(action: str, user=None, request=None, **metadata):
    """Create an AuditEvent. Never raises into the caller's request path."""
    try:
        from .models import AuditEvent

        request = request or get_current_request()
        if user is None and request is not None:
            u = getattr(request, "user", None)
            if u is not None and getattr(u, "is_authenticated", False):
                user = u
        return AuditEvent.objects.create(
            user=user if (user is not None and getattr(user, "pk", None)) else None,
            action=action,
            ip=client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:512] if request else ""),
            metadata=metadata or {},
        )
    except Exception:  # pragma: no cover - audit must never break the request
        logger.exception("failed to write audit event %s", action)
        return None
