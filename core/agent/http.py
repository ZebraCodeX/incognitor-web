"""Shared outbound HTTP helper for exposure sources.

Uses a pooled session, sensible timeouts and SSRF validation for every request
URL. Sources call :func:`request` instead of ``requests`` directly.
"""

import logging

import requests
from django.conf import settings

from core.services.ssrf import validate_outbound_url

logger = logging.getLogger(__name__)

USER_AGENT = "Incognitor-Sentinel/1.0 (+https://incognitor.app)"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


class SourceUnavailable(Exception):
    """Raised when a source cannot be reached (network/timeout)."""


def request(method, url, *, timeout=None, allow_private=False, **kwargs):
    """Perform a validated outbound HTTP request.

    ``allow_private`` is reserved for local test doubles; production code must
    leave it False.
    """
    if not allow_private:
        try:
            validate_outbound_url(url)
        except Exception as exc:  # noqa: BLE001 - surfaced as a source error
            raise SourceUnavailable(f"blocked URL {url}: {exc}") from exc

    timeout = timeout or getattr(settings, "SENTINEL_HTTP_TIMEOUT", 20)
    try:
        return _session.request(method, url, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise SourceUnavailable(str(exc)) from exc
