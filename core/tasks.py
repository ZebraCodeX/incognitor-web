from celery import shared_task
from django.utils import timezone
from .models import Scan
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
