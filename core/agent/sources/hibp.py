"""Have I Been Pwned breach + paste source.

Requires a paid HIBP API key (``HIBP_API_KEY``). The key is looked up with the
email address, which is why this source runs under the on-device agent (or with
an ephemeral identifier passed by the client); the server only persists the
resulting blind-indexed finding.
"""

import logging
import time
from datetime import date

from django.conf import settings

from ..base import ExposureSource, Finding
from ..http import SourceUnavailable, request

logger = logging.getLogger(__name__)

_API = "https://haveibeenpwned.com/api/v3"


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


class HaveIBeenPwnedSource(ExposureSource):
    name = "hibp"
    kind = "breach"
    disabled_reason = "HIBP_API_KEY not set"

    def is_configured(self):
        return bool(getattr(settings, "HIBP_API_KEY", ""))

    def search(self, identifiers, context=None):
        email = (identifiers or {}).get("email", "").strip()
        if not self.is_configured() or not email:
            return []
        headers = {"hibp-api-key": settings.HIBP_API_KEY}
        url = f"{_API}/breachedaccount/{email}?truncateResponse=false"
        try:
            resp = request("GET", url, headers=headers)
        except SourceUnavailable as exc:
            logger.warning("HIBP unavailable: %s", exc)
            return []
        if resp.status_code == 404:
            return []
        if resp.status_code == 429:
            logger.warning("HIBP rate limited")
            return []
        if resp.status_code != 200:
            logger.warning("HIBP unexpected status %s", resp.status_code)
            return []

        findings = []
        for breach in resp.json():
            findings.append(
                Finding(
                    source=self.name,
                    kind="breach",
                    title=f"Breach: {breach.get('Name', 'Unknown')}",
                    url=f"https://haveibeenpwned.com/PwnedWebsites#{breach.get('Name', '')}",
                    matched_kind="email",
                    matched_value=email,
                    breach_name=breach.get("Name", ""),
                    breach_date=_parse_date(breach.get("BreachDate")),
                    data_classes=breach.get("DataClasses", []),
                    pwn_count=breach.get("PwnCount", 0),
                    confidence=1.0,
                    metadata={"domain": breach.get("Domain", ""), "is_verified": breach.get("IsVerified", False)},
                )
            )
        # Be a good API citizen.
        time.sleep(1.6)
        return findings
