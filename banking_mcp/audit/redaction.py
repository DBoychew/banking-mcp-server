"""PII redaction utilities for banking audit logs."""

import re

# IBAN: keep first 4 + last 4, mask middle
_IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2})[A-Z0-9]{4,}([A-Z0-9]{4})\b")

# JWT tokens (eyJ...)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*\b")

# Basic auth header value (Basic base64...)
_BASIC_AUTH_RE = re.compile(r"\bBasic\s+[A-Za-z0-9+/=]+", re.IGNORECASE)

# Passwords / secrets in dicts — matches "password": "...", "secret": "..."
_SECRET_KEY_RE = re.compile(
    r'("(?:password|passwd|secret|token|api_key|authorization)"\s*:\s*")[^"]{4,}(")',
    re.IGNORECASE,
)

# Long numeric sequences that could be card/account numbers (12+ digits)
_LONG_NUMERIC_RE = re.compile(r"\b\d{12,}\b")


def redact(text: str) -> str:
    """Apply all PII redaction rules to a text string."""
    text = _IBAN_RE.sub(lambda m: m.group(1) + "****" + m.group(2), text)
    text = _JWT_RE.sub("[JWT_REDACTED]", text)
    text = _BASIC_AUTH_RE.sub("Basic [REDACTED]", text)
    text = _SECRET_KEY_RE.sub(r"\g<1>[REDACTED]\g<2>", text)
    text = _LONG_NUMERIC_RE.sub("[NUM_REDACTED]", text)
    return text


def redact_dict(data: dict) -> dict:
    """Redact sensitive values from a shallow dict (for logging tool args)."""
    _SENSITIVE_KEYS = frozenset(
        {"password", "passwd", "secret", "token", "api_key", "authorization", "auth"}
    )
    result = {}
    for k, v in data.items():
        if k.lower() in _SENSITIVE_KEYS:
            result[k] = "[REDACTED]"
        elif isinstance(v, str):
            result[k] = redact(v)
        else:
            result[k] = v
    return result
