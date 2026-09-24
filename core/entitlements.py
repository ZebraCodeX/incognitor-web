"""Plan entitlements.

Staff and superusers get **unlimited access to everything**. Everyone else is
limited by their plan. This is the single source of truth used by the API,
throttles and the agent, so privileged access is granted by Django's staff flag
(never by a hard-coded token).
"""

from dataclasses import dataclass

UNLIMITED = -1  # sentinel meaning "no limit"


@dataclass(frozen=True)
class Entitlements:
    plan: str
    is_staff: bool
    max_identities: int
    monitoring: bool
    auto_remove: bool
    dark_web: bool
    max_sends_per_day: int
    max_family_members: int
    priority_support: bool
    throttle_multiplier: int  # 0 = unlimited

    @property
    def unlimited(self) -> bool:
        return self.max_identities == UNLIMITED and self.max_sends_per_day == UNLIMITED

    def allows(self, feature: str) -> bool:
        return bool(getattr(self, feature, False))

    def within_identity_limit(self, current_count: int) -> bool:
        return self.max_identities == UNLIMITED or current_count < self.max_identities


_PLANS = {
    "free": Entitlements(
        plan="free", is_staff=False,
        max_identities=1, monitoring=True, auto_remove=False, dark_web=False,
        max_sends_per_day=20, max_family_members=0, priority_support=False,
        throttle_multiplier=1,
    ),
    "pro": Entitlements(
        plan="pro", is_staff=False,
        max_identities=10, monitoring=True, auto_remove=True, dark_web=True,
        max_sends_per_day=1000, max_family_members=0, priority_support=True,
        throttle_multiplier=5,
    ),
    "family": Entitlements(
        plan="family", is_staff=False,
        max_identities=25, monitoring=True, auto_remove=True, dark_web=True,
        max_sends_per_day=3000, max_family_members=6, priority_support=True,
        throttle_multiplier=10,
    ),
}

# Full, unrestricted access for the operator.
ADMIN_ENTITLEMENTS = Entitlements(
    plan="admin", is_staff=True,
    max_identities=UNLIMITED, monitoring=True, auto_remove=True, dark_web=True,
    max_sends_per_day=UNLIMITED, max_family_members=UNLIMITED, priority_support=True,
    throttle_multiplier=0,
)


def get_entitlements(user) -> Entitlements:
    """Resolve a user's entitlements. Staff/superusers are unlimited."""
    if user is None or not getattr(user, "is_authenticated", False):
        return _PLANS["free"]
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return ADMIN_ENTITLEMENTS
    profile = getattr(user, "profile", None)
    plan = getattr(profile, "plan", "free") or "free"
    return _PLANS.get(plan, _PLANS["free"])
