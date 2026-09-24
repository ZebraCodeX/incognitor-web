"""Rate-limit throttles with a staff bypass.

Staff and superusers are never rate limited (admin "free access"). All other
users get the configured scopes.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class StaffBypassMixin:
    def allow_request(self, request, view):
        user = getattr(request, "user", None)
        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
        ):
            return True
        return super().allow_request(request, view)


class BurstUserThrottle(StaffBypassMixin, UserRateThrottle):
    scope = "user"


class LoginRateThrottle(StaffBypassMixin, AnonRateThrottle):
    scope = "login"


class SignupRateThrottle(StaffBypassMixin, AnonRateThrottle):
    scope = "signup"


class AgentRateThrottle(StaffBypassMixin, UserRateThrottle):
    scope = "agent"
