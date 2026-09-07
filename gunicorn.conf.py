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