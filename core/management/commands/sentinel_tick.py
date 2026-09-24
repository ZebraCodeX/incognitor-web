"""Run a single Sentinel maintenance tick (queue monitors, verify, escalate).

Useful as a cron/systemd-timer replacement for Celery beat:

    python manage.py sentinel_tick
"""

from django.core.management.base import BaseCommand

from core.services.compliance import recompute_all
from core.tasks import process_user_campaigns, queue_due_watchlist_jobs


class Command(BaseCommand):
    help = "Queue due watchlist monitors, verify campaigns and escalate overdue ones."

    def handle(self, *args, **options):
        queued = queue_due_watchlist_jobs()
        campaigns = process_user_campaigns()
        scored = recompute_all()
        self.stdout.write(
            self.style.SUCCESS(
                f"Sentinel tick: {queued} monitor job(s) queued, "
                f"{campaigns['verification_jobs']} verification job(s), "
                f"{campaigns['escalations']} escalation(s), "
                f"{scored} broker score(s) updated."
            )
        )
