from celery import shared_task
from django.utils import timezone

from .agent import SentinelAgent
from .models import AgentJob, RemovalCampaign, Scan, Watchlist
from .services.scan_engine import ScanEngine


@shared_task
def run_scan(scan_id):
    """Celery task to run a privacy scan."""
    engine = ScanEngine(scan_id)
    engine.run()
    return {"scan_id": str(scan_id), "status": "completed"}


@shared_task
def run_recurring_scans():
    """Find all recurring scans that are due and run them."""
    now = timezone.now()
    due_scans = Scan.objects.filter(
        is_recurring=True,
        next_scan_date__lte=now,
        status__in=[Scan.Status.COMPLETED, Scan.Status.FAILED],
    )
    for scan in due_scans:
        new_scan = Scan.objects.create(
            user=scan.user,
            full_name=scan.full_name,
            email=scan.email,
            phone=scan.phone,
            address=scan.address,
            is_recurring=True,
            recurring_interval_days=scan.recurring_interval_days,
            next_scan_date=now + timezone.timedelta(days=scan.recurring_interval_days),
        )
        run_scan.delay(str(new_scan.id))
    return {"started": due_scans.count()}


# ---------------------------------------------------------------------------
# Sentinel agent tasks
# ---------------------------------------------------------------------------
def queue_due_watchlist_jobs(now=None):
    """Queue on-device MONITOR jobs for watchlists that are due."""
    now = now or timezone.now()
    queued = 0
    for watchlist in Watchlist.objects.filter(is_active=True, next_run_at__lte=now):
        already = AgentJob.objects.filter(
            watchlist=watchlist,
            job_type=AgentJob.Type.MONITOR,
            status__in=[
                AgentJob.Status.QUEUED,
                AgentJob.Status.CLAIMED,
                AgentJob.Status.RUNNING,
            ],
        ).exists()
        if not already:
            AgentJob.objects.create(
                user=watchlist.user,
                identity=watchlist.identity,
                watchlist=watchlist,
                job_type=AgentJob.Type.MONITOR,
            )
            queued += 1
        watchlist.next_run_at = now + timezone.timedelta(
            hours=max(watchlist.cadence_hours, 1)
        )
        watchlist.save(update_fields=["next_run_at"])
    return queued


def process_user_campaigns():
    """Verification + escalation pass for every user with live campaigns."""
    verified = escalated = 0
    user_ids = (
        RemovalCampaign.objects.exclude(
            status__in=[RemovalCampaign.Status.VERIFIED, RemovalCampaign.Status.CANCELLED]
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    from django.contrib.auth.models import User

    for user in User.objects.filter(id__in=list(user_ids)):
        agent = SentinelAgent(user)
        verified += agent.verify_due_campaigns()
        escalated += agent.escalate_overdue_campaigns()
    return {"verification_jobs": verified, "escalations": escalated}


@shared_task
def sentinel_tick():
    """Periodic Sentinel heartbeat: queue monitors, verify and escalate."""
    queued = queue_due_watchlist_jobs()
    campaigns = process_user_campaigns()
    from .services.compliance import recompute_all

    scored = recompute_all()
    return {"monitor_jobs": queued, "brokers_scored": scored, **campaigns}
