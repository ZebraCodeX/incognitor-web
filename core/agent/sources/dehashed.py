"""DeHashed breach/credential source.

Requires ``DEHASHED_EMAIL`` + ``DEHASHED_API_KEY``. Raw credential fields are
never persisted: only the fact that a class of data was exposed is retained.
"""

import logging

from django.conf import settings

from ..base import ExposureSource, Finding
from ..http import SourceUnavailable, request

logger = logging.getLogger(__name__)

_API = "https://api.dehashed.com/search"

# Fields that indicate a sensitive data class. Values are never stored.
_SENSITIVE_FIELDS = {
    "password": "Passwords",
    "hashed_password": "Hashed passwords",
    "phone": "Phone numbers",
    "address": "Physical addresses",
    "name": "Names",
    "username": "Usernames",
    "email": "Email addresses",
    "ssn": "Social Security numbers",
    "credit_card": "Credit cards",
    "bank_account": "Bank accounts",
    "dob": "Dates of birth",
    "ip_address": "IP addresses",
}


class DehashedSource(ExposureSource):
    name = "dehashed"
    kind = "breach"
    disabled_reason = "DEHASHED_EMAIL / DEHASHED_API_KEY not set"

    def is_configured(self):
        return bool(
            getattr(settings, "DEHASHED_EMAIL", "")
            and getattr(settings, "DEHASHED_API_KEY", "")
        )

    def search(self, identifiers, context=None):
        email = (identifiers or {}).get("email", "").strip()
        if not self.is_configured() or not email:
            return []
        auth = (settings.DEHASHED_EMAIL, settings.DEHASHED_API_KEY)
        params = {"query": f'email:"{email}"', "size": "100"}
        try:
            resp = request("GET", _API, params=params, auth=auth)
        except SourceUnavailable:
            return []
        if resp.status_code != 200:
            logger.warning("DeHashed unexpected status %s", resp.status_code)
            return []

        try:
            entries = resp.json().get("entries") or []
        except ValueError:
            return []

        findings = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            exposed = sorted(
                {label for field, label in _SENSITIVE_FIELDS.items() if entry.get(field)}
            )
            database = entry.get("database_name") or entry.get("database") or "unknown source"
            findings.append(
                Finding(
                    source=self.name,
                    kind="breach",
                    title=f"Credential/breach record: {database}",
                    matched_kind="email",
                    matched_value=email,
                    data_classes=exposed,
                    confidence=0.95,
                    metadata={"database": database, "exposed_fields": exposed},
                )
            )
        return findings
