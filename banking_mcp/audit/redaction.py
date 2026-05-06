"""PII redaction utilities.

Designed for SQL query strings and free-text error messages. Only redacts
content inside single-quoted SQL literals to avoid noisy false-positives
on numeric IDs, timestamps, etc.
"""

import re

# Email inside single quotes: 'user@host.tld'
_EMAIL_RE = re.compile(r"'[^']*@[^']*\.[^']*'", re.IGNORECASE)

# Phone numbers inside single quotes (10+ digits, possibly with separators)
_PHONE_RE = re.compile(r"'\+?[\d\s\-]{10,}'")

# Long string literals inside single quotes (likely PII)
_LONG_STR_RE = re.compile(r"'[^']{20,}'")


def redact(text: str) -> str:
    """Redact PII from a string (SQL query or message)."""
    if not text:
        return text
    text = _EMAIL_RE.sub("'<EMAIL>'", text)
    text = _PHONE_RE.sub("'<PHONE>'", text)
    text = _LONG_STR_RE.sub("'<REDACTED>'", text)
    return text
