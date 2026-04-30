from __future__ import annotations

from typing import Any

import jwt

from banking_mcp.config import settings


class TokenError(ValueError):
    """Raised when a JWT token is invalid or expired."""


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Validate and decode the backend-issued JWT access token.

    Must use the same JWT_SECRET_KEY / JWT_ALGORITHM as the issuing backend.
    Raises TokenError on any validation failure.
    """
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
            },
        )
    except Exception as exc:
        raise TokenError("Invalid or expired token") from exc


def require_subject(payload: dict[str, Any]) -> str:
    """Extract and return the 'sub' claim, raising TokenError if absent."""
    sub = payload.get("sub")
    if not sub:
        raise TokenError("Token missing subject")
    return str(sub)
