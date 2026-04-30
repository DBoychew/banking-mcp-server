import re
from dataclasses import dataclass
from typing import Any, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

STRICT_CONFIRM_PATTERNS = [
    r"^\s*(?:потвърждавам)\s*$",
    r"^\s*(?:потвърди)\s*$",
    r"^\s*confirm\s*$",
    r"^\s*yes\s*,?\s*confirm\s*$",
    r"^\s*proceed\s*$",
]

SOFT_CONFIRM_PATTERNS = [
    r"^\s*(?:да)\s*$",
    r"^\s*(?:да)\s*,?\s*(?:потвърждавам)\s*$",
    r"^\s*(?:да)\s*,?\s*(?:потвърди)\s*$",
    r"^\s*(?:да)\s*,?\s*(?:искам)\s*$",
    r"^\s*yes\s*$",
    r"^\s*ok\s*$",
    r"^\s*okay\s*$",
]


def is_explicit_confirmation(text: str) -> bool:
    """Handle is explicit confirmation."""
    t = (text or "").strip().lower()
    return any(re.match(p, t) for p in STRICT_CONFIRM_PATTERNS) or any(
        re.match(p, t) for p in SOFT_CONFIRM_PATTERNS
    )


def is_strict_confirmation(text: str) -> bool:
    """Return True only for explicit transfer-confirmation phrases."""
    t = (text or "").strip().lower()
    return any(re.match(p, t) for p in STRICT_CONFIRM_PATTERNS)


def is_soft_confirmation(text: str) -> bool:
    """Return True for generic affirmations such as 'yes' or 'да'."""
    t = (text or "").strip().lower()
    return any(re.match(p, t) for p in SOFT_CONFIRM_PATTERNS)


@dataclass
class PendingTransfer:
    """Represents PendingTransfer."""

    from_account_id: str
    amount: str
    currency: str
    idempotency_key: str
    to_account_id: Optional[str] = None
    to_iban: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Handle to dict."""
        return {
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
            "to_iban": self.to_iban,
            "amount": self.amount,
            "currency": self.currency,
            "description": self.description,
            "idempotency_key": self.idempotency_key,
        }


class PendingActionSigner:
    """Signed token so client cannot tamper with previewed transfer data."""

    def __init__(self, secret: str, salt: str = "pending-transfer-v1"):
        """Initialize the instance."""
        self.serializer = URLSafeTimedSerializer(secret_key=secret, salt=salt)

    def sign(self, payload: dict[str, Any]) -> str:
        """Sign."""
        return self.serializer.dumps(payload)

    def unsign(self, token: str, *, max_age_seconds: int = 10 * 60) -> dict[str, Any]:
        """Verify and decode."""
        try:
            data = self.serializer.loads(token, max_age=max_age_seconds)
            if not isinstance(data, dict):
                raise ValueError("Invalid token payload type")
            return data
        except SignatureExpired as exc:
            raise ValueError("Confirmation token expired") from exc
        except BadSignature as exc:
            raise ValueError("Invalid or expired confirmation token") from exc
