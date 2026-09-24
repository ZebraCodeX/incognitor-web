"""Verifiable removal receipts.

Every evidence entry for a campaign is appended to a per-campaign hash chain:
``entry_hash = SHA256(prev_hash | canonical(entry))``. Anyone can later replay
the chain to prove a receipt existed and was not altered — useful when
escalating to regulators. Payloads contain no plaintext PII.
"""

import hashlib
import json

from core.models import RemovalEvidence


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _entry_hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256(f"{prev_hash}|{_canonical(entry)}".encode("utf-8")).hexdigest()


def append(campaign, kind: str, payload: dict | None = None, ciphertext: bytes | None = None):
    """Append a new hash-chained evidence entry to a campaign."""
    payload = payload or {}
    last = campaign.evidence.order_by("-sequence").first()
    sequence = (last.sequence + 1) if last else 0
    prev_hash = last.entry_hash if last else ""
    entry = {
        "campaign": str(campaign.id),
        "sequence": sequence,
        "kind": kind,
        "payload": payload,
    }
    entry_hash = _entry_hash(prev_hash, entry)
    return RemovalEvidence.objects.create(
        campaign=campaign,
        kind=kind,
        ciphertext=ciphertext,
        sha256=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
        sequence=sequence,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        metadata=payload,
    )


def verify_chain(campaign) -> dict:
    """Return ``{"valid": bool, "length": int, "broken_at": int|None}``."""
    prev_hash = ""
    count = 0
    for evidence in campaign.evidence.order_by("sequence"):
        entry = {
            "campaign": str(campaign.id),
            "sequence": evidence.sequence,
            "kind": evidence.kind,
            "payload": evidence.metadata or {},
        }
        expected = _entry_hash(prev_hash, entry)
        if expected != evidence.entry_hash or evidence.prev_hash != prev_hash:
            return {"valid": False, "length": count, "broken_at": evidence.sequence}
        prev_hash = evidence.entry_hash
        count += 1
    return {"valid": True, "length": count, "broken_at": None}
