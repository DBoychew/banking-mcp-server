from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple


GENERIC_COUNTERPARTY_TOKENS = {
    "transaction",
    "transactions",
    "activity",
    "history",
    "statement",
    "statements",
    "show",
    "list",
    "transfers",
}


def currency_norm(value: Any) -> Optional[str]:
    """Normalize currency aliases/symbols to 3-letter uppercase code when possible."""
    if value is None:
        return None
    raw = str(value).strip().replace(".", "")
    upper = raw.upper().replace(" ", "")
    lower = raw.lower().strip()

    if upper in {"BGN", "ЛВ"} or lower in {"лв", "лев", "лева"}:
        return "BGN"
    if upper in {"EUR"} or raw in {"€", "€"} or lower in {"евро"}:
        return "EUR"
    if upper in {"USD"} or raw in {"$", "$"}:
        return "USD"
    if len(upper) == 3:
        return upper
    return upper or None


def amount_norm(value: Any) -> Optional[str]:
    """Normalize amount to decimal string with 2 digits, rejecting non-positive values."""
    if value is None:
        return None
    try:
        raw = str(value).strip().replace(",", ".")
        dec = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if dec <= 0:
        return None
    dec = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(dec, "f")


def normalize_entities(
    intent: str, entities: Dict[str, Any]
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Normalize entities and guard against common hallucinations.
    Returns (normalized_entities, optional_ask_message).
    """
    normalized = dict(entities or {})

    if "currency" in normalized:
        normalized["currency"] = currency_norm(normalized.get("currency"))

    if "period" in normalized and normalized["period"]:
        period = str(normalized["period"]).strip().lower()
        allowed = {
            "today",
            "yesterday",
            "this_week",
            "last_week",
            "this_month",
            "last_month",
            "last_7_days",
            "last_30_days",
        }
        aliases = {
            "last7days": "last_7_days",
            "last30days": "last_30_days",
            "7days": "last_7_days",
            "30days": "last_30_days",
        }
        period = aliases.get(period, period)
        normalized["period"] = period if period in allowed else normalized["period"]

    for key in ("counterparty_query", "exclude_counterparty_query"):
        token = str(normalized.get(key) or "").strip().lower()
        if not token:
            continue
        if (
            token in GENERIC_COUNTERPARTY_TOKENS
            or len(token) <= 2
            or "transaction" in token
            or "history" in token
            or "statement" in token
            or "извлеч" in token
            or "транзак" in token
            or "истори" in token
            or "движен" in token
        ):
            normalized.pop(key, None)

    if intent != "prepare_transfer":
        return normalized, None

    if "amount" in normalized:
        normalized["amount"] = amount_norm(normalized.get("amount"))

    if not normalized.get("currency"):
        normalized["currency"] = "BGN"

    has_to_account = bool(normalized.get("to_account_id"))
    has_to_iban = bool(normalized.get("to_iban"))
    if has_to_account and has_to_iban:
        return normalized, (
            "I see both **to_account_id** and **IBAN**. Which destination should I use?\n"
            "- Reply with either: 'to IBAN ...' **or** 'to account id ...'"
        )

    return normalized, None
