"""Core types for the Sentinel exposure-monitoring agent."""

from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass
class Finding:
    """A single potential exposure discovered by a source.

    ``matched_value`` holds the plaintext identifier transiently so the
    orchestrator can compute a blind index and then discard it. It is never
    persisted to the database.
    """

    source: str
    kind: str
    title: str
    url: str = ""
    severity: str = "medium"
    matched_kind: str = ""
    matched_value: str = ""
    masked_evidence: str = ""
    confidence: float = 0.7
    breach_name: str = ""
    breach_date: date | None = None
    data_classes: list = field(default_factory=list)
    pwn_count: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        data = asdict(self)
        if self.breach_date:
            data["breach_date"] = self.breach_date.isoformat()
        # Never leak the raw matched value.
        data.pop("matched_value", None)
        return data


class ExposureSource:
    """Base class for a pluggable exposure data source."""

    name = "base"
    kind = "other"
    #: Human-readable reason shown when the source is not usable.
    disabled_reason = "not configured"

    def is_configured(self) -> bool:
        return False

    def search(self, identifiers: dict, context: dict | None = None) -> list[Finding]:
        """Return findings for the given plaintext ``identifiers``.

        ``identifiers`` is a transient dict such as
        ``{"email": ..., "phone": ..., "full_name": ..., "address": ...}``.
        Implementations must not persist it.
        """
        raise NotImplementedError


def build_query_terms(identifiers: dict) -> list[str]:
    """Build likely search query strings from identifiers (used by web search)."""
    terms = []
    name = identifiers.get("full_name", "").strip()
    email = identifiers.get("email", "").strip()
    phone = identifiers.get("phone", "").strip()
    city = identifiers.get("city", "").strip()
    state = identifiers.get("state", "").strip()
    if name:
        if city or state:
            terms.append(" ".join(t for t in [name, city, state] if t))
        terms.append(f'"{name}"')
        if email:
            terms.append(f'"{name}" "{email}"')
    if email:
        terms.append(f'"{email}"')
    if phone:
        terms.append(f'"{phone}"')
    # de-duplicate while preserving order
    seen = set()
    unique = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:6]
