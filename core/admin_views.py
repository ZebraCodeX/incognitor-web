"""Staff-only operator console (server-rendered) for platform oversight.

Complements the JSON admin API at ``/api/admin/``. Every mutating action is
audit-logged. Access requires Django's staff flag.
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .audit import record as audit_record
from .models import (
    AgentJob,
    AuditEvent,
    Broker,
    Exposure,
    Household,
    Identity,
    Notification,
    RemovalCampaign,
    UserProfile,
)
from .services.compliance import recompute_all, score_broker


def _stats():
    return {
        "users": User.objects.count(),
        "staff": User.objects.filter(is_staff=True).count(),
        "identities": Identity.objects.count(),
        "households": Household.objects.count(),
        "exposures": Exposure.objects.count(),
        "exposures_by_severity": {
            r["severity"]: r["count"]
            for r in Exposure.objects.values("severity").annotate(count=Count("id"))
        },
        "campaigns": RemovalCampaign.objects.count(),
        "campaigns_by_status": {
            r["status"]: r["count"]
            for r in RemovalCampaign.objects.values("status").annotate(count=Count("id"))
        },
        "agent_jobs": AgentJob.objects.count(),
        "queued_jobs": AgentJob.objects.filter(status="queued").count(),
        "notifications": Notification.objects.count(),
        "brokers": Broker.objects.count(),
    }


@staff_member_required
def console_overview(request):
    recent = AuditEvent.objects.select_related("user")[:25]
    return render(
        request,
        "core/console/overview.html",
        {"stats": _stats(), "recent_events": recent},
    )


@staff_member_required
def console_users(request):
    q = request.GET.get("q", "").strip()
    users = User.objects.select_related("profile").order_by("-date_joined")
    if q:
        users = users.filter(Q(username__icontains=q) | Q(email__icontains=q))
    return render(
        request,
        "core/console/users.html",
        {"users": users[:200], "q": q, "plans": UserProfile.Plan.choices},
    )


@staff_member_required
@require_POST
def console_user_action(request, user_id):
    target = get_object_or_404(User, id=user_id)
    action = request.POST.get("action")
    if action == "set_plan":
        plan = request.POST.get("plan")
        if plan in dict(UserProfile.Plan.choices):
            profile, _ = UserProfile.objects.get_or_create(user=target)
            profile.plan = plan
            profile.save(update_fields=["plan"])
            audit_record("admin.console.set_plan", user=request.user,
                         target=target.username, plan=plan)
            messages.success(request, f"{target.username} → {plan} plan.")
    elif action == "toggle_staff":
        target.is_staff = not target.is_staff
        target.save(update_fields=["is_staff"])
        audit_record("admin.console.toggle_staff", user=request.user,
                     target=target.username, is_staff=target.is_staff)
        messages.success(request, f"{target.username} staff={target.is_staff}.")
    return redirect("console_users")


@staff_member_required
def console_exposures(request):
    severity = request.GET.get("severity")
    qs = Exposure.objects.select_related("user", "breach_event")
    if severity:
        qs = qs.filter(severity=severity)
    return render(
        request,
        "core/console/exposures.html",
        {"exposures": qs[:200], "severity": severity},
    )


@staff_member_required
def console_campaigns(request):
    status = request.GET.get("status")
    qs = RemovalCampaign.objects.select_related("user", "broker", "exposure")
    if status:
        qs = qs.filter(status=status)
    return render(
        request,
        "core/console/campaigns.html",
        {"campaigns": qs[:200], "status": status},
    )


@staff_member_required
def console_brokers(request):
    brokers = Broker.objects.all()
    return render(request, "core/console/brokers.html", {"brokers": brokers})


@staff_member_required
@require_POST
def console_broker_action(request, broker_id):
    broker = get_object_or_404(Broker, id=broker_id)
    action = request.POST.get("action")
    if action == "toggle_active":
        broker.is_active = not broker.is_active
        broker.save(update_fields=["is_active"])
        audit_record("admin.console.broker_toggle", user=request.user,
                     broker=broker.name, is_active=broker.is_active)
        messages.success(request, f"{broker.name} active={broker.is_active}.")
    elif action == "rescore":
        score_broker(broker)
        messages.success(request, f"Rescored {broker.name}.")
    return redirect("console_brokers")


@staff_member_required
@require_POST
def console_rescore_all(request):
    count = recompute_all()
    messages.success(request, f"Rescored {count} broker(s).")
    return redirect("console_brokers")
