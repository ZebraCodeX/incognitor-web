"""Exposure triage: severity scoring, fingerprinting and de-duplication."""

import hashlib

from .base import Finding

# Data classes ranked by how damaging their exposure is.
_CRITICAL_CLASSES = {
    "social security numbers", "ssn", "passports", "credit cards",
    "bank accounts", "financial data", "government issued ids",
    "partial credit card data", "credit card cvv", "tax records",
}
_HIGH_CLASSES = {
    "passwords", "hashed passwords", "phone numbers", "physical addresses",
    "dates of birth", "geographic locations", "health records",
    "auth tokens", "security questions and answers",
}
_MEDIUM_CLASSES = {
    "email addresses", "names", "usernames", "ip addresses",
    "device information", "browsing histories",
}


def score_severity(finding: Finding) -> str:
    classes = {str(c).strip().lower() for c in (finding.data_classes or [])}
    if finding.kind in {"dark_web", "canary"}:
        return "critical"
    if classes & _CRITICAL_CLASSES:
        return "critical"
    if classes & _HIGH_CLASSES:
        return "high"
    if finding.kind in {"people_search", "public_record"}:
        return "high" if finding.kind == "people_search" else "medium"
    if finding.kind == "breach":
        # Lower confidence / no sensitive classes still matters.
        return "high" if classes else "medium"
    if classes & _MEDIUM_CLASSES:
        return "medium"
    return "low"


def fingerprint(finding: Finding, blind_index_value: str = "") -> str:
    parts = [
        finding.source or "",
        finding.kind or "",
        finding.breach_name or "",
        finding.url or "",
        blind_index_value or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Drop findings with identical (source, kind, url, breach) fingerprints."""
    seen = {}
    for finding in findings:
        key = (finding.source, finding.kind, finding.url, finding.breach_name)
        existing = seen.get(key)
        if existing is None or finding.confidence > existing.confidence:
            seen[key] = finding
    return list(seen.values())


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def sort_by_severity(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9), -f.confidence),
    )
