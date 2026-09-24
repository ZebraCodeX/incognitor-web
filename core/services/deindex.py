"""Pre-index / cache de-listing helpers.

Broker opt-outs remove the source page, but search engines often keep a cached
copy. This module decides when to request de-indexing and builds the payload the
on-device agent submits to each engine's content-removal endpoint.
"""

from django.conf import settings

DEINDEXABLE_KINDS = {"search_result", "people_search", "public_record"}


def should_deindex(exposure) -> bool:
    return bool(exposure.url) and exposure.kind in DEINDEXABLE_KINDS


def configured_engines() -> list[str]:
    engines = []
    if getattr(settings, "GOOGLE_DEINDEX_ENDPOINT", ""):
        engines.append("google")
    if getattr(settings, "BING_DEINDEX_ENDPOINT", ""):
        engines.append("bing")
    return engines


def build_deindex_payload(exposure) -> dict:
    """Payload for the on-device agent to POST to each engine."""
    return {
        "url": exposure.url,
        "title": exposure.title,
        "reason": "personal_information",
        "jurisdiction": "CCPA/CPRA, GDPR",
        "engines": configured_engines() or ["google", "bing"],
    }
