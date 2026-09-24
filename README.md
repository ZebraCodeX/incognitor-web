# Incognitor Web 🛡️

Django + DRF backend for **Incognitor**: continuous personal-data monitoring and
automatic removal from data brokers, people-search sites and breaches.

Companion projects: `incognitor-desktop` (on-device executor) and
`incognitor-extension` (browser extension).

## Features

- **Sentinel agent** — monitors breaches (HIBP, DeHashed), web/people-search,
  pastes, public code, licensed dark-web feeds; matches, triages and dedupes.
- **Automatic removal** — CCPA/CPRA/GDPR/state-law letters, web-form submission,
  deadline tracking and regulator escalation.
- **Alerts** — in-app feed, email, SSE, signed webhooks, Web Push (VAPID).
- **Differentiators** — canary/tripwire identities, per-broker aliases,
  provenance graph, pre-index de-listing, hash-chained receipts, compliance scores.
- **Zero-knowledge** — PII is encrypted client-side; the server stores only
  ciphertext + HMAC blind indexes.
- **Plans & admin** — clear entitlements; staff get unlimited access.
- **Security** — fail-fast secrets, HSTS/CSP, Argon2id, TOTP MFA, throttling,
  SSRF guards, append-only audit log.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # generate keys (see file comments)
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_brokers
.venv/bin/python manage.py runserver
```

Optional background workers:

```bash
.venv/bin/celery -A incognitor worker -l info
.venv/bin/celery -A incognitor beat -l info   # scans daily, Sentinel every 30m
```

## Architecture

```
on-device agent (vault key)            server (blind coordinator)
──────────────────────────            ──────────────────────────
Argon2id → AES-256-GCM                 ciphertext + blind indexes only
supplies identifiers for a run   →     HMAC-matches, discards plaintext
claims AgentJobs, decrypts,      ←     queues removal/verify/escalate
sends email / drives web forms         never sees plaintext PII
```

## Admin access

```bash
python manage.py grant_admin <username>          # is_staff + is_superuser
python manage.py grant_admin --revoke <username>
```

Staff bypass all rate limits and quotas and can reach `/console/` and
`/api/admin/`. Entitlements live in `core/entitlements.py`.

## Key endpoints

- `POST /api/auth/login|signup|logout/`, `token/`, `mfa_*`, `verify_email`
- `GET /api/brokers/`, `POST/GET /api/scans/`, `/api/data-stops/`
- `CRUD /api/identities/` (+ `canary/`, `alias/`), `/api/watchlists/`
- `GET /api/exposures/` (+ `dismiss`, `request_removal`, `provenance`)
- `GET /api/removal-campaigns/` (+ `verify_ledger`), `/api/notifications/` (+ SSE)
- `CRUD /api/households/`, `/api/notification-channels/`, `/api/push/`
- `POST /api/agent/run/`, `GET/claim/complete /api/agent/jobs/`

## Tests & checks

```bash
.venv/bin/python manage.py test tests
.venv/bin/ruff check core incognitor tests
.venv/bin/bandit -r core incognitor -c bandit.yaml
```

## Legal

Generates legally-standard opt-out requests but cannot guarantee broker
compliance. Monitor only identifiers you are authorised to act on.
