#!/usr/bin/env bash
# Incognitor Web — quick launcher.
#   ./run.sh web       -> Django web dashboard + API
#   ./run.sh setup     -> first-time setup (venv, migrate, seed brokers)
#   ./run.sh worker    -> Celery worker
#   ./run.sh beat      -> Celery beat
#   ./run.sh test      -> run tests
set -euo pipefail
cd "$(dirname "$0")"

CMD="${1:-setup}"

case "$CMD" in
  setup)
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python manage.py migrate
    .venv/bin/python manage.py seed_brokers
    echo "✔ Done. Create a superuser with: .venv/bin/python manage.py createsuperuser"
    ;;
  web)
    .venv/bin/python manage.py runserver "${2:-127.0.0.1:8000}"
    ;;
  worker)
    .venv/bin/celery -A incognitor worker -l info
    ;;
  beat)
    .venv/bin/celery -A incognitor beat -l info
    ;;
  test)
    .venv/bin/python manage.py test tests
    ;;
  *)
    echo "Usage: $0 {setup|web|worker|beat|test}"
    exit 1
    ;;
esac