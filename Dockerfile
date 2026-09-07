# Incognitor web app — Fly.io image.
# Base is the official Playwright Python image so Chromium + browser libs are
# preinstalled for the web-form removal automation.
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Byte-compile for faster first requests + collect static for Whitenoise.
RUN python -m compileall -q incognitor core || true \
    && python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8080
CMD ["gunicorn", "incognitor.wsgi:application", "--config", "gunicorn.conf.py"]