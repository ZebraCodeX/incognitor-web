"""Canary / tripwire and per-broker alias identifiers.

A **canary** is a unique synthetic identifier registered with exactly one broker.
If it later appears in a breach dump or on another broker, the server has proof
that the designated broker leaked or sold the record.

An **alias** is a throwaway address given to a specific broker (e.g. email
plus-addressing). Any future exposure matching the alias is attributed to that
broker.

Plaintext values are used only to compute the blind index and are not stored.
"""

import secrets

from core.crypto import blind_index, mask_identifier


def build_alias(base_identifier: str, broker_slug: str, kind: str = "email") -> str:
    """Generate a deterministic-format, unique alias for a broker."""
    token = secrets.token_hex(4)
    slug = (broker_slug or "broker").lower()
    if kind == "email" and "@" in base_identifier:
        local, _, domain = base_identifier.partition("@")
        return f"{local}+{slug}-{token}@{domain}"
    if kind == "phone":
        digits = "".join(c for c in base_identifier if c.isdigit())
        return f"{digits}+{token}"
    return f"{base_identifier}-{slug}-{token}"


def register_identifier(identity, kind: str, value: str, role: str,
                        linked_broker=None, masked: str | None = None):
    """Store an identifier transiently as blind index + mask (no plaintext)."""
    from core.models import IdentityIdentifier

    return IdentityIdentifier.objects.update_or_create(
        identity=identity,
        kind=kind,
        blind_index=blind_index(kind, value),
        defaults={
            "masked_value": masked or mask_identifier(kind, value),
            "role": role,
            "linked_broker": linked_broker,
        },
    )


def create_canary(identity, broker, base_identifier: str, kind: str = "email"):
    """Create a canary identifier for a broker and return it."""
    value = build_alias(base_identifier, broker.slug if broker else "unknown", kind)
    identifier, _ = register_identifier(
        identity, kind, value, role="canary", linked_broker=broker
    )
    return identifier, value


def create_alias(identity, broker, base_identifier: str, kind: str = "email"):
    value = build_alias(base_identifier, broker.slug if broker else "unknown", kind)
    identifier, _ = register_identifier(
        identity, kind, value, role="alias", linked_broker=broker
    )
    return identifier, value
