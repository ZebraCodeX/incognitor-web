# Incognitor Web — Fly.io go-live runbook

Target: one Fly.io app with three processes (`web`, `worker`, `beat`) + a managed
Redis (Fly.io Redis) + a persistent volume for the SQLite database.

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
fly launch --no-deploy --name incognitor --copy-config
```

(`incognitor` must be globally unique — if taken, change the `app` name in `fly.toml`
to e.g. `incognitor-privacy` and the CSRF_TRUSTED_ORIGINS below to match.)

## 2. Persistent SQLite volume

```bash
fly volumes create incognitor_data --size 1
```

This mounts at `/app/data` (set in `fly.toml [mounts]`); `DB_PATH=/app/data/db.sqlite3`
keeps the database across deploys.

## 3. Managed Redis (for Celery worker/beat)

```bash
fly redis create --name incognitor-redis --size 1
fly redis status incognitor-redis
fly redis connect incognitor-redis
```

Copy the connection string (looks like `redis://default:xxxx@incognitor-redis.internal:6379`)
and store it:

```bash
fly secrets set \
  CELERY_BROKER_URL="redis://default:xxxx@incognitor-redis.internal:6379" \
  CELERY_RESULT_BACKEND="redis://default:xxxx@incognitor-redis.internal:6379"
```

## 4. Secrets (never commit these)

```bash
fly secrets set DJANGO_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))')"

# Real outbound opt-out emails (see README). Use an app-specific password.
fly secrets set EMAIL_HOST_USER="your-privacy-account@gmail.com"
fly secrets set EMAIL_HOST_PASSWORD="your-app-password"
```

> Without `EMAIL_*` secrets, emails go to the Django *console* backend (safe test mode).
> Set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` too:

```bash
fly secrets set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

## 5. Deploy

```bash
fly deploy
```

The `release_command` runs `migrate` + `seed_brokers` on every deploy before the
new version serves traffic.

```bash
fly scale count web=1 worker=1 beat=1   # ensure all three run
fly status
```

## 6. Verify

```bash
curl -f https://incognitor.fly.dev/                          # landing page
curl -f https://incognitor.fly.dev/api/brokers/ -o /dev/null -w "%{http_code}\n"  # 403 (auth required — good)
fly logs
fly scale show
```

Create your admin, then open the dashboard URL and sign up normally:

```bash
fly ssh console -C "python manage.py createsuperuser"
```

## 7. Custom domain (optional, recommended for email deliverability)

```bash
fly certs add privacy.example.com
```

Then add `privacy.example.com` to `[env] ALLOWED_HOSTS` and
`https://privacy.example.com` to `CSRF_TRUSTED_ORIGINS` in `fly.toml`, redeploy,
and point DNS A/AAAA (or CNAME) at your Fly app. Configure SPF/DKIM/DMARC for
the sending domain so opt-out emails don't land in spam.

## 8. Connect the desktop client

```bash
export INCOGNITOR_API_URL="https://incognitor.fly.dev/api/"
python -m desktop.main
```

## Ops cheat-sheet

```bash
fly logs                       # tail logs (all processes)
fly logs -i                    # process-filtered
fly scale count worker=1       # scale a process
fly ssh console                # get a shell in the web machine
fly volumes list
fly redis status incognitor-redis

# Backups — the SQLite volume lives on a single machine; snapshot regularly:
fly volumes snapshot -a incognitor incognitor_data
```

## Costs (ballpark, 2026)

- 3x shared-cpu-1x VMs + small volume + Tiny Redis ≈ **$9–12/mo**
- Scale the `web` VM down to a single machine if you want to shave a few dollars
  (worker + beat are lightweight).

## Gotchas

- **SQLite + concurrent writes**: the worker/beat/web all write one SQLite file on
  the volume. Fine for a single-user tool; if multi-user traffic grows, swap to
  Postgres (`fly postgres create` + set `DATABASES` via env).
- **`release_command` runs `seed_brokers`** — idempotent, safe to run on every deploy.
- **Playwright chromium** ships in the base image; web-form brokers will then
  actually fill forms instead of showing "failed".
- **Fly lock-in on the app name** — if you want `incognitor.fly.dev`, claim it early.