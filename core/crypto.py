"""Cryptographic helpers for the zero-knowledge vault and blind indexes.

Two primitives are used:

* **Blind index** -- a deterministic, keyed HMAC-SHA256 over a normalized
  identifier. The server stores only these digests, so it can match an
  identifier across breach feeds, brokers and exposure records without ever
  handling the plaintext value.
* **Field encryption** -- Fernet (AES-128-CBC + HMAC) for server-held secrets
  such as webhook signing keys. User PII is encrypted client-side with a key the
  server never sees; this is only for server-managed secrets.

Both are keyed from settings so keys can be rotated via environment variables.
"""

import base64
import hashlib
import hmac
import re

from django.conf import settings

try:  # cryptography is an optional-but-recommended dependency
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - exercised only in minimal installs
    Fernet = None

    class InvalidToken(Exception):
        pass


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NON_DIGIT = re.compile(r"\D+")


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str) -> str:
    digits = _NON_DIGIT.sub("", value or "")
    return f"+{digits}" if digits else ""


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def normalize_identifier(kind: str, value: str) -> str:
    kind = (kind or "").lower()
    if kind == "email":
        return normalize_email(value)
    if kind == "phone":
        return normalize_phone(value)
    if kind in {"full_name", "name", "username"}:
        return normalize_name(value)
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(normalize_email(value)))


# ---------------------------------------------------------------------------
# Blind index
# ---------------------------------------------------------------------------
def _blind_key() -> bytes:
    key = getattr(settings, "BLIND_INDEX_KEY", None) or settings.SECRET_KEY
    return key.encode("utf-8")


def blind_index(kind: str, value: str) -> str:
    """Return a hex HMAC-SHA256 blind index for an identifier.

    The same (kind, normalized value) always yields the same digest, which lets
    the server join identifiers across sources without storing the value.
    """
    normalized = normalize_identifier(kind, value)
    if not normalized:
        return ""
    msg = f"{kind}:{normalized}".encode("utf-8")
    return hmac.new(_blind_key(), msg, hashlib.sha256).hexdigest()


def hmac_sha256(value: str, key: bytes | None = None) -> str:
    key = key or _blind_key()
    return hmac.new(key, (value or "").encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Masking (safe to display / log)
# ---------------------------------------------------------------------------
def mask_identifier(kind: str, value: str) -> str:
    kind = (kind or "").lower()
    value = value or ""
    if not value:
        return ""
    if kind == "email":
        name, _, domain = value.partition("@")
        if not domain:
            return value[:2] + "***"
        shown = name[:1] if name else ""
        return f"{shown}***@{domain}"
    if kind == "phone":
        digits = _NON_DIGIT.sub("", value)
        return f"***-***-{digits[-4:]}" if len(digits) >= 4 else "***"
    if kind in {"full_name", "name"}:
        parts = value.split()
        return " ".join(p[:1] + "***" for p in parts)
    if kind in {"ssn", "national_id", "passport"}:
        return "***-**-" + value[-4:] if len(value) >= 4 else "***"
    return value[:1] + "***" if len(value) > 1 else "***"


# ---------------------------------------------------------------------------
# Field encryption (server-managed secrets only)
# ---------------------------------------------------------------------------
def _fernet() -> "Fernet":
    if Fernet is None:  # pragma: no cover
        raise RuntimeError("cryptography is required for field encryption")
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not key:
        # Derive a stable key from SECRET_KEY when not explicitly configured.
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode("ascii")
    return Fernet(key if isinstance(key, bytes) else key.encode("utf-8"))


def encrypt_text(plaintext: str) -> bytes:
    if plaintext in (None, ""):
        return b""
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_text(token: bytes) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(bytes(token)).decode("utf-8")
    except InvalidToken:
        return ""


def generate_field_key() -> str:
    """Utility for operators: print a new FIELD_ENCRYPTION_KEY value."""
    if Fernet is None:  # pragma: no cover
        raise RuntimeError("cryptography is required to generate keys")
    return Fernet.generate_key().decode("ascii")
