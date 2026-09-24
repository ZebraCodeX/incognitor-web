"""Provenance: attribute an exposure to the broker that most likely leaked it.

Three signals, strongest first:

1. **Canary** -- the record contains a tripwire registered with one broker, so
   that broker (or a buyer of its data) leaked it.
2. **Alias** -- the record contains a per-broker throwaway alias.
3. **Correlation** -- the same blind index appears across several brokers; the
   one with the most "superspreader" overlap is the likely upstream source.
"""

from collections import Counter

from core.models import Exposure, IdentityIdentifier


def _identifier_for(user, blind_index_value: str):
    if not blind_index_value:
        return None
    return (
        IdentityIdentifier.objects.filter(
            identity__user=user,
            blind_index=blind_index_value,
            role__in=[IdentityIdentifier.Role.CANARY, IdentityIdentifier.Role.ALIAS],
        )
        .select_related("linked_broker")
        .first()
    )


def attribute(exposure: Exposure) -> dict:
    """Compute a provenance dict for an exposure (without saving)."""
    blind = exposure.matched_blind_index
    provenance = {"via": "unknown", "shared_count": 0, "brokers": []}

    identifier = _identifier_for(exposure.user, blind)
    if identifier and identifier.linked_broker:
        provenance.update(
            {
                "via": identifier.role,
                "likely_source_broker": str(identifier.linked_broker_id),
                "likely_source_broker_name": identifier.linked_broker.name,
                "is_canary": identifier.role == "canary",
            }
        )

    if blind:
        siblings = (
            Exposure.objects.filter(user=exposure.user, matched_blind_index=blind)
            .exclude(id=exposure.id)
            .values_list("source", "site_domain", "title")
        )
        domains = Counter()
        for source, domain, title in siblings:
            domains[domain or source or title.split()[0]] += 1
        provenance["shared_count"] = sum(domains.values())
        provenance["brokers"] = [d for d, _ in domains.most_common(5)]

    return provenance


def refresh_exposure(exposure: Exposure) -> dict:
    provenance = attribute(exposure)
    exposure.provenance = provenance
    exposure.save(update_fields=["provenance"])
    return provenance
