"""Public-records source (pluggable provider).

Public-records aggregators each have their own API/shape, so this source is a
thin, configurable adapter: point ``PUBLIC_RECORDS_API_URL`` at an aggregator
that accepts a ``query`` parameter and returns JSON records. When unset the
source is disabled.
"""

import logging

from django.conf import settings

from ..base import ExposureSource, Finding
from ..http import SourceUnavailable, request

logger = logging.getLogger(__name__)


class PublicRecordsSource(ExposureSource):
    name = "public_records"
    kind = "public_record"
    disabled_reason = "PUBLIC_RECORDS_API_URL not set"

    def is_configured(self):
        return bool(getattr(settings, "PUBLIC_RECORDS_API_URL", ""))

    def search(self, identifiers, context=None):
        if not self.is_configured():
            return []
        query = (identifiers or {}).get("full_name", "").strip()
        if not query:
            return []
        headers = {}
        if getattr(settings, "PUBLIC_RECORDS_API_KEY", ""):
            headers["Authorization"] = f"Bearer {settings.PUBLIC_RECORDS_API_KEY}"
        try:
            resp = request(
                "GET",
                settings.PUBLIC_RECORDS_API_URL,
                headers=headers,
                params={"query": query},
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
                    kind="public_record",
                    title=record.get("title") or "Public record match",
                    url=record.get("url", ""),
                    matched_kind="full_name",
                    matched_value=query,
                    confidence=float(record.get("confidence", 0.6)),
                    metadata={"record_type": record.get("type", "")},
                )
            )
        return findings
