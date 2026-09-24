"""Web Push (VAPID) notifications for the web app.

Operators configure a VAPID key pair (``VAPID_PUBLIC_KEY`` / ``VAPID_PRIVATE_KEY``
/ ``VAPID_ADMIN_EMAIL``); generate one with::

    python manage.py generate_vapid_keys

If unconfigured, :func:`send_push` is a no-op so nothing breaks in dev.

The service worker JS is served from the site root (``/sw.js``) so it can
control the whole origin.
"""

import json
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(getattr(settings, "VAPID_PRIVATE_KEY", ""))


def public_key() -> str:
    return getattr(settings, "VAPID_PUBLIC_KEY", "")


def _claims() -> dict:
    email = getattr(settings, "VAPID_ADMIN_EMAIL", "") or "admin@incognitor.app"
    return {"sub": f"mailto:{email}"}


def send_push(user, title: str, body: str = "", data: dict | None = None) -> int:
    """Send a push to every active subscription. Returns the number sent."""
    if not is_configured():
        return 0
    from pywebpush import WebPushException, webpush

    from core.models import PushSubscription

    payload = json.dumps({"title": title, "body": body, "data": data or {}})
    sent = 0
    for sub in PushSubscription.objects.filter(user=user, is_active=True):
        try:
            webpush(
                subscription_info=sub.as_info(),
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=_claims(),
                timeout=15,
            )
            sub.last_used_at = timezone.now()
            sub.save(update_fields=["last_used_at"])
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                sub.is_active = False
                sub.save(update_fields=["is_active"])
            else:
                logger.warning("web push failed for %s: %s", sub.id, exc)
        except Exception:  # noqa: BLE001
            logger.exception("web push unexpected error")
    return sent


# Served from /sw.js so it controls the whole origin.
SERVICE_WORKER_JS = """
self.addEventListener('push', function (event) {
  let payload = { title: 'Incognitor', body: '' };
  try { payload = event.data ? event.data.json() : payload; } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(payload.title || 'Incognitor', {
      body: payload.body || '',
      icon: '/static/icons/icon128.png',
      badge: '/static/icons/icon48.png',
      data: payload.data || {},
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/exposures/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (const client of list) {
        if (client.url.indexOf(url) !== -1 && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
"""
