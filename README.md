# Incognitor Web 🛡️

**Django web app + API that deletes your personal information from the internet.**

This is the backend half of Incognitor: a multi-user web dashboard and JSON API
used by the [`incognitor-desktop`](https://github.com/ZebraCodeX/incognitor-desktop)
PyQt6 client.

Give it a name and email and it:

1. **Scans** 43 data brokers, people-search sites, background-check services and
   public-records aggregators.
2. **Submits removal requests** automatically — legally-formatted opt-out emails
   (CCPA/CPRA/GDPR) and headless-browser web-form filling.
3. **Stops data selling** — formal “stop selling/sharing/marketing my data”
   opt-outs.
4. **Tracks everything** — live progress, per-broker status, recurring scans.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_brokers        # loads 43 real-world brokers

# optional: web-form automation browsers
.venv/bin/pip install playwright && .venv/bin/playwright install chromium

.venv/bin/python manage.py runserver           # http://127.0.0.1:8000
.venv/bin/python manage.py createsuperuser
```

Background workers (optional; falls back to threads without Redis):

```bash
.venv/bin/celery -A incognitor worker -l info
.venv/bin/celery -A incognitor beat -l info     # recurring scans daily at 6:00
```

## How a scan works

`core.services.scan_engine.ScanEngine` walks every active broker and, based on
its `removal_method`:

- `email` → builds a personalized CCPA/CPRA/GDPR deletion letter and emails the
  broker’s opt-out address
- `web_form` → drives Chromium (Playwright) to fill and submit the opt-out form
- `manual` → flags as *Needs Manual Action* with the opt-out URL ready to click

Every request is recorded as a `RemovalRequest` with status, evidence and error
history. The **Data Stops** page sends a separate letter asking brokers to stop
selling, sharing and marketing your data (CPRA §1798.120).

## API

DRF-style, session auth + CSRF:

- `POST /api/auth/login|signup|logout/`
- `GET /api/brokers/`
- `POST /api/scans/`, `GET /api/scans/`, `POST /api/scans/{id}/start/`,
  `GET /api/scans/{id}/status/`
- `GET /api/data-stops/`, `POST /api/data-stops/bulk_submit/`

Emails print to the console by default; set the `EMAIL_*` SMTP variables in a
`.env` file (see `.env.example`) to send real opt-out letters.

## Tests

```bash
.venv/bin/python manage.py test tests
```

## Legal note

Generates legally-standard opt-out requests (GDPR/CCPA/CPRA) but can’t guarantee
broker compliance; some brokers require ID verification. For persistent
non-compliance, file a complaint with your state AG or the CFPB.
