"""Dark-web exposure source (licensed feeds only).

Incognitor does not crawl Tor or scrape criminal marketplaces. This adapter
consumes a licensed breach-intelligence feed (commercial providers expose REST
APIs). Configure ``DARKWEB_FEED_URL`` and optionally ``DARKWEB_FEED_API_KEY``.
Until configured the source is disabled, which is the safe default.
"""

import logging

from django.conf import settings

from ..base import ExposureSource, Finding
from ..http import SourceUnavailable, request

logger = logging.getLogger(__name__)


class DarkWebSource(ExposureSource):
    name = "dark_web"
    kind = "dark_web"
    disabled_reason = "DARKWEB_FEED_URL not set (licensed feed required)"

    def is_configured(self):
        return bool(getattr(settings, "DARKWEB_FEED_URL", ""))

    def search(self, identifiers, context=None):
        if not self.is_configured():
            return []
        email = (identifiers or {}).get("email", "").strip()
        if not email:
            return []
        headers = {}
        if getattr(settings, "DARKWEB_FEED_API_KEY", ""):
            headers["Authorization"] = f"Bearer {settings.DARKWEB_FEED_API_KEY}"
        try:
            resp = request(
                "GET", settings.DARKWEB_FEED_URL, headers=headers, params={"query": email}
            )
        except SourceUnavailable:
            return []
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []
        records = payload if isinstance(payload, list) else payload.get("results", [])
        findings = []
        for record in records:
            if not isinstance(record, dict):
                continue
            findings.append(
                Finding(
                    source=self.name,
                    kind="dark_web",
                    title=record.get("title") or "Dark-web mention",
                    url="",  # never link to illicit marketplaces
                    matched_kind="email",
                    matched_value=email,
                    data_classes=record.get("data_classes", []),
                    confidence=float(record.get("confidence", 0.7)),
                    metadata={"feed": record.get("feed", "")},
                )
            )
        return findings
