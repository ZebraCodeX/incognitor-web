import logging
import threading
import time

from django.utils import timezone

from core.models import Scan
from core.services.scan_engine import ScanEngine

logger = logging.getLogger(__name__)


def start_scan_in_thread(scan):
    """Run a scan on a daemon thread. Falls back to a background scan when Celery
    is not configured, so a single-machine deploy never depends on a broker."""
    scan_ref = scan.id

    def _run():
        try:
            ScanEngine(scan_ref).run()
        except Exception as e:
            s = Scan.objects.get(id=scan_ref)
            s.status = Scan.Status.FAILED
            s.error_message = str(e)
            s.save()
            logger.exception("scan %s failed", scan_ref)

    threading.Thread(target=_run, daemon=True).start()


def _due_recurring_scan(scan, now):
    return (
        scan.is_recurring
        and scan.next_scan_date is not None
        and scan.next_scan_date <= now
        and scan.status in [Scan.Status.COMPLETED, Scan.Status.FAILED]
    )


def run_scheduler(interval_seconds=600):
    """Periodically launch due recurring scans. Runs each scan in a thread so the
    web machine needs no background worker/broker."""
    logger.info("recurring-scan scheduler started")
    while True:
        try:
            now = timezone.now()
            due = [
                scan
                for scan in Scan.objects.filter(is_recurring=True).select_related("user")
                if _due_recurring_scan(scan, now)
            ]
            for source in due:
                logger.info("recurring scan due: %s", source.id)
                new_scan = Scan.objects.create(
                    user=source.user,
                    full_name=source.full_name,
                    email=source.email,
                    phone=source.phone,
                    address=source.address,
                    is_recurring=True,
                    recurring_interval_days=source.recurring_interval_days,
                    next_scan_date=timezone.now()
                    + timezone.timedelta(days=source.recurring_interval_days),
                )
                start_scan_in_thread(new_scan)
        except Exception:
            logger.exception("scheduler tick failed")
        time.sleep(interval_seconds)