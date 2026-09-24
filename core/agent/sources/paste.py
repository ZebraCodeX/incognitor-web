"""HIBP paste-account source (public paste sites pastes)."""

import time

from django.conf import settings

from ..base import ExposureSource, Finding
from ..http import SourceUnavailable, request

_API = "https://haveibeenpwned.com/api/v3"


class PasteSource(ExposureSource):
    name = "paste"
    kind = "paste"
    disabled_reason = "HIBP_API_KEY not set"

    def is_configured(self):
        return bool(getattr(settings, "HIBP_API_KEY", ""))

    def search(self, identifiers, context=None):
        email = (identifiers or {}).get("email", "").strip()
        if not self.is_configured() or not email:
            return []
        headers = {"hibp-api-key": settings.HIBP_API_KEY}
        url = f"{_API}/pasteaccount/{email}"
        try:
            resp = request("GET", url, headers=headers)
        except SourceUnavailable:
            return []
        if resp.status_code != 200:
            return []

        findings = []
        for paste in resp.json():
            source = paste.get("Source", "paste")
            paste_id = paste.get("Id", "")
            findings.append(
                Finding(
                    source=self.name,
                    kind="paste",
                    title=f"Paste exposure via {source}",
                    url=(
                        f"https://pastebin.com/{paste_id}"
                        if source.lower() == "pastebin" and paste_id
                        else ""
                    ),
                    matched_kind="email",
                    matched_value=email,
                    data_classes=paste.get("DataClasses", []),
                    confidence=0.9,
                    metadata={
                        "paste_source": source,
                        "email_count": paste.get("EmailCount", 0),
                    },
                )
            )
        time.sleep(1.6)
        return findings
