"""User notifications: in-app, email and signed webhooks (Slack/Discord/etc.)."""

import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings
from django.core.mail import EmailMessage

from core.crypto import decrypt_text

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _meets_threshold(threshold: str, severity: str) -> bool:
    return _SEVERITY_RANK.get(severity, 0) >= _SEVERITY_RANK.get(threshold, 1)


def notify(user, title: str, body: str = "", severity: str = "medium", exposure=None):
    """Persist an in-app notification and fan it out to configured channels."""
    from core.models import Notification, NotificationChannelConfig

    notification = Notification.objects.create(
        user=user, title=title, body=body, severity=severity, exposure=exposure
    )

    for channel in NotificationChannelConfig.objects.filter(user=user, is_active=True):
        if not _meets_threshold(channel.severity_threshold, severity):
            continue
        try:
            _dispatch(channel, user, title, body, severity)
        except Exception:  # noqa: BLE001 - one bad channel must not break others
            logger.exception("notification channel %s failed", channel.kind)

    # Always email the account address for high/critical findings.
    if severity in {"high", "critical"} and user.email:
        try:
            EmailMessage(
                subject=f"[Incognitor] {title}",
                body=body or title,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            ).send()
        except Exception:  # noqa: BLE001
            logger.exception("notification email failed for %s", user.username)

    # Web Push to subscribed browsers.
    try:
        from core.services import push

        push.send_push(user, title, body, {"url": "/exposures/"})
    except Exception:  # noqa: BLE001
        logger.exception("web push dispatch failed")

    return notification


def _dispatch(channel, user, title, body, severity):
    # Channel targets (webhook URLs, chat IDs) are encrypted at rest.
    target = decrypt_text(channel.target.encode("utf-8")) or channel.target
    payload = {
        "event": "exposure",
        "severity": severity,
        "title": title,
        "body": body,
        "user": user.username,
    }
    if channel.kind == "email":
        EmailMessage(
            subject=f"[Incognitor] {title}",
            body=body or title,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[target],
        ).send()
        return

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = decrypt_text(bytes(channel.signing_secret)) if channel.signing_secret else ""
    if secret:
        headers["X-Incognitor-Signature"] = hmac.new(
            secret.encode("utf-8"), data, hashlib.sha256
        ).hexdigest()

    if channel.kind == "telegram":
        # target is "bot_token:chat_id"
        token, _, chat_id = target.partition(":")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": f"{title}\n{body}"}, timeout=10)
        return

    # Generic webhook (Slack/Discord/Signal bridges accept JSON POSTs).
    from core.services.ssrf import validate_outbound_url

    validate_outbound_url(target)
    requests.post(target, data=data, headers=headers, timeout=10)
