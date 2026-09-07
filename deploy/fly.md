# Incognitor Web — Fly.io go-live runbook

Target: one Fly.io app with a single machine (`app` process) + a persistent volume
for the SQLite database. Scans, opt-out emails, and web-form fillers all run
in-process inside gunicorn's worker threads, so no Redis, worker, or beat process
is needed.

## 0. Prereqs

```bash
# Install flyctl + login
curl -L https://fly.io/install.sh | sh
fly auth login

# Local docker for building the image (optional; Fly can build remotely too)
docker --version
```

## 1. Create the app

```bash
cd incognitor-web
fly apps create incognitor      # --org personal
```

(`incognitor` must be globally unique — if taken, change the `app` name in
`fly.toml` to e.g. `incognitor-privacy` and the CSRF_TRUSTED_ORIGINS below to match.)

## 2. Persistent SQLite volume

```bash
fly volumes create incognitor_data --size 1 --region lax
```

This mounts at `/app/data` (set in `fly.toml [mounts]`); `DB_PATH=/app/data/db.sqlite3`
keeps the database across deploys. Only ONE volume should be attached — it's the
live database.

## 3. Secrets (never commit these)

```bash
fly secrets set DJANGO_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))')"

# Real outbound opt-out emails (see README). Use an app-specific password.
fly secrets set EMAIL_HOST_USER="your-privacy-account@gmail.com"
fly secrets set EMAIL_HOST_PASSWORD="your-app-password"
```

> Without `EMAIL_*` secrets, emails go to the Django *console* backend (safe test
> mode — you'll see them in `fly logs`). Set
> `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` to send for real:

```bash
fly secrets set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

## 4. Deploy

```bash
fly deploy
```

`entrypoint.sh` (the container command, wired via `[processes] app`) runs
`manage.py migrate` + `seed_brokers` before exec'ing gunicorn — on the same
machine and volume, so there is no separate release-machine DB problem.
The gunicorn master also starts the recurring-scan scheduler thread
(`core/runner.py run_scheduler`) every 10 minutes.

## 5. Verify

```bash
curl -f https://incognitor.fly.dev/                          # landing page
curl -f https://incognitor.fly.dev/api/brokers/ -o /dev/null -w "%{http_code}\n"  # 403 (auth required — good)
fly status                # should show ONE machine, state started, checks passing
fly logs                  # watch opt-out emails / scan progress
```

Create your admin, then open the dashboard URL and sign up normally:

```bash
fly ssh console -a incognitor -C "python manage.py createsuperuser"
```

## 6. Custom domain (optional, recommended for email deliverability)

```bash
fly certs add privacy.example.com
```

Then add `privacy.example.com` to `[env] ALLOWED_HOSTS` and
`https://privacy.example.com` to `CSRF_TRUSTED_ORIGINS` in `fly.toml`, redeploy,
and point DNS A/AAAA (or CNAME) at your Fly app. Configure SPF/DKIM/DMARC for
the sending domain so opt-out emails don't land in spam.

## 7. Connect the desktop client

```bash
export INCOGNITOR_API_URL="https://incognitor.fly.dev/api/"
python -m desktop.main
```

## Ops cheat-sheet

```bash
fly logs                            # tail app logs
fly status                          # machine state + checks
fly ssh console -a incognitor       # get a shell in the app machine
fly volumes list -a incognitor      # expect ONE attached volume
fly scale show -a incognitor
```

# Backups — the SQLite volume lives on a single machine; snapshot regularly:
fly volumes snapshot -a incognitor incognitor_data

## Costs (ballpark, 2026)

- 1x shared-cpu-1x VM + 1GB volume ≈ **$4–5/mo**

## Gotchas

- **One machine, one volume, one SQLite file** — don't add a second web machine
  while on SQLite; the file isn't shared between machines.
- **Web-form removal is best-effort** — most opt-out sites block bots (Cloudflare,
  captchas), so `removal_method=web_form` brokers usually end up "failed"; the
  **email path (CCPA/CPRA/GDPR letters) is the reliable one** and is what the
  scan reports as `removed_count`.
- **Scans run in gunicorn worker threads** — deploy/restart kills an in-flight scan.
  Re-start it from the dashboard; recurring scans are re-looked-up every 10 min.
- **Playwright chromium** ships in the base image; the engine launches it with
  `--no-sandbox --disable-dev-shm-usage` and caps each form at 90s so one stuck
  site can't freeze the scan.
- **Fly lock-in on the app name** — if you want `incognitor.fly.dev`, claim it early.