import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "incognitor.settings")

app = Celery("incognitor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "run-due-recurring-scans": {
        "task": "core.tasks.run_recurring_scans",
        "schedule": crontab(hour=6, minute=0),  # daily at 6:00
    },
}