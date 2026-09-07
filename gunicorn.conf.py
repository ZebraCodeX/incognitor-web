"""Gunicorn config for Incognitor on Fly.io."""

import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = 120

worker_class = "gthread"
accesslog = "-"
errorlog = "-"
capture_output = True


def on_starting(server):
    """Start the in-process recurring-scan scheduler in the master, so a single
    machine needs no Celery worker or beat."""
    import os
    import threading

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "incognitor.settings")
    import django

    django.setup()

    from core import runner

    threading.Thread(target=runner.run_scheduler, daemon=True).start()