# Incognitor Web 🛡️

**Django web app + API that deletes your personal information from the internet — automatically.**

This is the **backend half** of Incognitor: a multi-user web dashboard and JSON API used by the
[`incognitor-desktop`](https://github.com/ZebraCodeX/incognitor-desktop) PyQt6 client.

Give it a name and email and it:

1. **Scans** 43 data brokers, people-search sites, background-check services, and public-records aggregators
2. **Submits removal requests** automatically — legally-formatted opt-out emails (CCPA/CPRA/GDPR) *and* headless-browser web-form filling
3. **Stops data selling** — formal "stop selling/sharing/marketing my data" opt-outs
4. **Tracks everything** — live progress, per-broker status, recurring scans so listings don't return

---

## Quick Start

### Prerequisites
- Python 3.11+
- Redis (for Celery background jobs — optional, falls back to threads)
- Chromium (for web-form filling — optional, email-only mode works without it)

```bash
cd incognitor-web

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_brokers        # loads 43 real-world brokers

# Optional: web-form automation browsers
.venv/bin/pip install playwright && .venv/bin/playwright install chromium

.venv/bin/python manage.py runserver           # http://127.0.0.1:8000
.venv/bin/python manage.py createsuperuser
```

### Background workers (optional but recommended)

```bash
.venv/bin/celery -A incognitor worker -l info   # runs scans asynchronously
.venv/bin/celery -A incognitor beat -l info     # recurring scans daily at 6:00
```

> Without Redis/Celery, scans still work — the API falls back to a background thread.

---

## Configuring Real Emails

Default: emails print to the console (safe for testing). To send real opt-out letters:

```bash
# .env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-privacy-account@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL="Privacy Requests <your-privacy-account@gmail.com>"
```

---

## How a Scan Works

`core.services.scan_engine.ScanEngine` walks every active broker and, based on each broker's `removal_method`:
- **`email`** → builds a personalized CCPA/CPRA/GDPR deletion letter and emails the broker's opt-out address
- **`web_form`** → drives Chromium (Playwright) to open the opt-out page, fill the form, and submit
- **`both`** → does both
- **`manual`** → flags as *Needs Manual Action* with the opt-out URL ready to click

Every request is recorded as a `RemovalRequest` with status, evidence, and error history. The **Data Stops** page sends a separate opt-out letter asking brokers to stop *selling*, *sharing*, and *using your data for marketing* (CPRA §1798.120).

---

## API (used by the desktop client)

DRF-style, session auth + CSRF:

- `POST /api/auth/login|signup|logout/`
- `GET /api/brokers/`
- `POST /api/scans/`, `GET /api/scans/`, `POST /api/scans/{id}/start/`, `GET /api/scans/{id}/status/`
- `GET /api/data-stops/`, `POST /api/data-stops/bulk_submit/`

The PyQt6 client for this API is in the `incognitor-desktop` repo.

---

## Architecture

```
incognitor/                 # Django project (settings, urls, celery beat)
├── core/
│   ├── models.py           # UserProfile, Broker, Scan, RemovalRequest, DataStopRequest, ActivityLog
│   ├── api.py              # DRF viewsets used by the desktop client
│   ├── services/
│   │   ├── scan_engine.py  # orchestrates a full scan
│   │   ├── email_engine.py # legally-formatted opt-out emails
│   │   └── web_form_engine.py  # Playwright form-filling automation
│   ├── tasks.py            # Celery tasks + recurring scheduler
│   └── management/commands/seed_brokers.py
├── templates/core/         # Tailwind web dashboard
└── tests/                  # model + engine + API tests
```

## Tests

```bash
.venv/bin/python manage.py test tests
```

## Legal Note

This generates legally-standard opt-out requests (GDPR/CCPA/CPRA) but can't guarantee broker compliance. Removal timelines vary (brokers legally get 30–45 days); some require ID verification — watch **Needs Manual Action** items. For persistent non-compliance, file a complaint with your state AG or the CFPB.