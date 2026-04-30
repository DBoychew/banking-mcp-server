"""
Provider auth helpers for MCP tool context.

In MCP, tools receive no HTTP headers — authentication is either:
  (a) Service mode: credentials from env vars (EBANK_USERNAME / EBANK_PASSWORD)
  (b) Delegated mode: caller passes an 'authorization' string in tool arguments

This module provides utilities to build and validate authorization strings
so they can be forwarded to the eBank adapter.
"""

from __future__ import annotations

import base64
import json
from typing import Optional


def build_basic_authorization(username: str, password: str) -> str:
    """Encode username:password as a Basic authorization string."""
    raw = f"{username}:{password}"
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def build_ebank_session_authorization(
    session_id: str,
    *,
    lang: str = "BG",
    user_id: str = "",
    customer_id: str = "",
) -> str:
    """Encode an eBank session payload as an EbankSession authorization string."""
    payload = {
        "sessid": session_id,
        "lang": lang,
        "userid": user_id,
        "customerid": customer_id,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"EbankSession {encoded}"


def extract_user_id_from_authorization(authorization: Optional[str]) -> Optional[str]:
    """
    Best-effort extraction of user_id from an authorization string.
    Supports Basic (returns username) and EbankSession (returns userid field).
    Returns None if extraction fails.
    """
    raw = str(authorization or "").strip()
    if not raw:
        return None

    parts = raw.split(" ", 1)
    if len(parts) != 2:
        return None

    scheme, token = parts[0].lower(), parts[1].strip()

    if scheme == "basic":
        try:
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.b64decode(padded).decode("utf-8")
            return decoded.split(":", 1)[0].strip() or None
        except Exception:
            return None

    if scheme in {"ebanksession", "bearer"}:
        try:
            padded = token + "=" * (-len(token) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            return (
                str(payload.get("userid") or payload.get("user_id") or "").strip()
                or None
            )
        except Exception:
            return None

    return None
