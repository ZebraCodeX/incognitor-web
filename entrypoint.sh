#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py seed_brokers

exec gunicorn incognitor.wsgi:application -c gunicorn.conf.py