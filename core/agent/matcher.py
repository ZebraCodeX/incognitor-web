"""Identifier matching and confidence scoring.

Given free text (a search snippet, a broker page) and the subject's identifiers,
:func:`match_text` reports which identifier matched and how confident we are.
"""

import re

from ..crypto import normalize_phone

# A small nickname map to catch obvious variants. Extendable.
_NICKNAMES = {
    "william": {"bill", "billy", "will", "willy"},
    "robert": {"bob", "bobby", "rob"},
    "richard": {"rick", "dick", "rich"},
    "james": {"jim", "jimmy", "jamie"},
    "margaret": {"maggie", "peggy", "meg"},
    "elizabeth": {"liz", "beth", "betty", "lizzy"},
    "jennifer": {"jen", "jenny"},
    "katherine": {"kate", "kathy", "katie", "kat"},
    "michael": {"mike", "mikey"},
    "christopher": {"chris"},
    "daniel": {"dan", "danny"},
    "joseph": {"joe", "joey"},
    "edward": {"ed", "ted", "ned"},
    "anthony": {"tony"},
}

_WORD = re.compile(r"[a-z0-9@.+\-]+")


def name_variants(full_name: str) -> set[str]:
    """Return normalized name variants (full, reversed, nicknames)."""
    name = re.sub(r"\s+", " ", (full_name or "").strip().lower())
    if not name:
        return set()
    parts = name.split()
    variants = {name}
    if len(parts) >= 2:
        variants.add(" ".join(reversed(parts)))
        first = parts[0]
        if first in _NICKNAMES:
            for nick in _NICKNAMES[first]:
                variants.add(" ".join([nick] + parts[1:]))
    return variants


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def match_text(text: str, identifiers: dict) -> dict:
    """Return ``{"score", "kind", "value"}`` for the strongest match.

    Scores: exact email 1.0, phone 0.9, full-name variant 0.7, partial name 0.4.
    """
    haystack = _normalize_text(text)
    if not haystack:
        return {"score": 0.0, "kind": "", "value": ""}

    email = (identifiers or {}).get("email", "").strip().lower()
    if email and email in haystack:
        return {"score": 1.0, "kind": "email", "value": email}

    phone = normalize_phone((identifiers or {}).get("phone", ""))
    if phone:
        digits = re.sub(r"\D", "", phone)
        if len(digits) >= 7 and digits[-7:] in re.sub(r"\D", "", haystack):
            return {"score": 0.9, "kind": "phone", "value": phone}

    full_name = (identifiers or {}).get("full_name", "")
    variants = name_variants(full_name)
    if variants and any(v in haystack for v in variants):
        return {"score": 0.7, "kind": "full_name", "value": full_name}

    # Partial: all words of the name appear somewhere in the text.
    parts = [p for p in re.sub(r"\s+", " ", full_name.strip().lower()).split() if len(p) > 2]
    if parts and all(p in haystack for p in parts):
        return {"score": 0.4, "kind": "full_name", "value": full_name}

    return {"score": 0.0, "kind": "", "value": ""}
