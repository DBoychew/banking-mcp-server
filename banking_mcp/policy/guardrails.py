from dataclasses import dataclass
from typing import Any, Optional
import re

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass
class GuardrailResult:
    """Represents policy validation result for a user turn."""

    allowed: bool
    reason: Optional[str] = None


def validate_turn_policy(
    *,
    me: dict[str, Any],
    intent: str,
    entities: dict[str, Any],
) -> GuardrailResult:
    """Validate whether the requested intent/entities are policy compliant."""
    role = str(me.get("role") or "user").lower()
    is_frozen = bool(me.get("is_frozen", False))

    if is_frozen and intent == "prepare_transfer":
        return GuardrailResult(
            allowed=False,
            reason="Account operations are blocked because this user is currently frozen.",
        )

    if intent == "admin" and role != "admin":
        return GuardrailResult(allowed=False, reason="Admin-only action denied.")

    if intent == "prepare_transfer":
        currency = entities.get("currency")
        if currency and not _CURRENCY_RE.match(str(currency).upper()):
            return GuardrailResult(
                allowed=False,
                reason="Currency must be a valid 3-letter code.",
            )

        amount = entities.get("amount")
        if amount is not None:
            try:
                numeric = float(str(amount))
            except ValueError:
                return GuardrailResult(
                    allowed=False,
                    reason="Amount format is invalid.",
                )
            if numeric <= 0:
                return GuardrailResult(
                    allowed=False,
                    reason="Amount must be greater than zero.",
                )

    return GuardrailResult(allowed=True)
