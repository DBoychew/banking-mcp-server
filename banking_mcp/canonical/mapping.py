from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

MISSING = object()
TransformFn = Callable[[Any], Any]
DefaultValue = Any

CANONICAL_MAPPING_VERSION = "v1"

ENTITY_ACCOUNT = "account"
ENTITY_TRANSACTION = "transaction"
ENTITY_TRANSFER = "transfer"
ENTITY_STATEMENT = "statement"


@dataclass(frozen=True)
class FieldMapping:
    aliases: tuple[str, ...]
    transform: TransformFn | None = None
    required: bool = False
    default: DefaultValue = MISSING


@dataclass(frozen=True)
class EntityMapping:
    version: str
    fields: Mapping[str, FieldMapping]


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _resolve_default(default: DefaultValue) -> Any:
    return default() if callable(default) else default


def _lookup_key_ci(data: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    if key in data:
        return True, data[key]
    wanted = key.lower()
    for candidate, candidate_value in data.items():
        if isinstance(candidate, str) and candidate.lower() == wanted:
            return True, candidate_value
    return False, None


def _resolve_path(data: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = data
    for segment in path.split("."):
        if not isinstance(current, Mapping):
            return False, None
        found, current = _lookup_key_ci(current, segment)
        if not found:
            return False, None
    return True, current


def resolve_first_alias(payload: Any, aliases: tuple[str, ...]) -> Any:
    if not isinstance(payload, Mapping):
        return MISSING
    for alias in aliases:
        found, value = _resolve_path(payload, alias)
        if not found or is_missing_value(value):
            continue
        return value
    return MISSING


def map_entity_fields(payload: Any, mapping: EntityMapping) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None

    out: dict[str, Any] = {}
    for field_name, spec in mapping.fields.items():
        raw_value = resolve_first_alias(payload, spec.aliases)
        if raw_value is MISSING:
            if spec.default is not MISSING:
                out[field_name] = _resolve_default(spec.default)
                continue
            if spec.required:
                return None
            continue

        value = raw_value
        if spec.transform is not None:
            try:
                value = spec.transform(raw_value)
            except Exception:
                value = MISSING

        if value is MISSING or is_missing_value(value):
            if spec.default is not MISSING:
                out[field_name] = _resolve_default(spec.default)
                continue
            if spec.required:
                return None
            continue

        out[field_name] = value

    return out


def to_stripped_string(value: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return MISSING
    return raw


def to_upper_token(value: Any) -> Any:
    raw = str(value or "").strip().upper()
    if not raw:
        return MISSING
    return raw


def to_lower_token(value: Any) -> Any:
    raw = str(value or "").strip().lower()
    if not raw:
        return MISSING
    return raw


def to_iban(value: Any) -> Any:
    raw = str(value or "").replace(" ", "").strip().upper()
    if not raw:
        return MISSING
    return raw


def to_decimal_text(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return MISSING
    if isinstance(value, Decimal):
        return format(value, "f")

    raw = str(value).strip()
    if not raw:
        return MISSING
    normalized = raw.replace(" ", "").replace(",", ".")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation:
        return MISSING
    return format(parsed, "f")


def to_int_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return MISSING
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            return MISSING
        return int(value)

    normalized = str(value).strip().replace(",", ".")
    if not normalized:
        return MISSING
    try:
        parsed = Decimal(normalized)
    except InvalidOperation:
        return MISSING

    if parsed != parsed.to_integral_value():
        return MISSING
    return int(parsed)


def to_datetime_value(value: Any) -> Any:
    if value is None:
        return MISSING
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if abs(timestamp) > 1_000_000_000_000:
            timestamp /= 1000.0
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    raw = str(value).strip()
    if not raw:
        return MISSING

    candidate = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        pass

    for pattern in ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, pattern)
            return parsed
        except ValueError:
            continue
    return raw


def normalize_direction(value: Any) -> str:
    token = str(to_lower_token(value) or "").strip()
    if token in {"credit", "cr", "incoming", "in", "deposit", "received"}:
        return "credit"
    if token in {"debit", "dr", "outgoing", "out", "withdrawal", "withdraw", "sent"}:
        return "debit"
    return "unknown"


def normalize_status(value: Any) -> Any:
    token = to_lower_token(value)
    if token is MISSING:
        return MISSING
    aliases = {
        "ok": "active",
        "enabled": "active",
        "blocked": "blocked",
        "disabled": "inactive",
        "done": "executed",
        "completed": "executed",
        "cancelled": "canceled",
        "canceled": "canceled",
        "error": "failed",
    }
    return aliases.get(str(token), str(token))


ACCOUNT_MAPPING_V1 = EntityMapping(
    version=CANONICAL_MAPPING_VERSION,
    fields={
        "account_id": FieldMapping(
            aliases=(
                "account_id",
                "accountId",
                "accountid",
                "id",
                "account.id",
                "account_number",
                "accountNumber",
                "number",
            ),
            transform=to_stripped_string,
            required=True,
        ),
        "iban": FieldMapping(
            aliases=(
                "iban",
                "IBAN",
                "accountIban",
                "account_iban",
                "accountIBAN",
                "account.iban",
            ),
            transform=to_iban,
        ),
        "currency": FieldMapping(
            aliases=(
                "currency",
                "currencyCode",
                "curr",
                "currdt",
                "currkt",
                "ccy",
                "accountCurrency",
                "account.currency",
                "account.currencyCode",
            ),
            transform=to_upper_token,
            required=True,
        ),
        "balance": FieldMapping(
            aliases=(
                "balance",
                "available_balance",
                "availableBalance",
                "available",
                "availbal",
                "current_balance",
                "currentBalance",
                "amount",
            ),
            transform=to_decimal_text,
            default="0",
        ),
        "status": FieldMapping(
            aliases=(
                "status",
                "state",
                "stateid",
                "accountStatus",
                "account.status",
            ),
            transform=normalize_status,
        ),
        "provider_account_id": FieldMapping(
            aliases=(
                "provider_account_id",
                "providerAccountId",
                "id",
                "account.id",
            ),
            transform=to_stripped_string,
        ),
    },
)


TRANSACTION_MAPPING_V1 = EntityMapping(
    version=CANONICAL_MAPPING_VERSION,
    fields={
        "transaction_id": FieldMapping(
            aliases=("transaction_id", "transactionId", "txn_id", "txnId", "id"),
            transform=to_stripped_string,
        ),
        "account_id": FieldMapping(
            aliases=(
                "account_id",
                "accountId",
                "account.id",
                "source_account_id",
                "sourceAccountId",
            ),
            transform=to_stripped_string,
        ),
        "amount": FieldMapping(
            aliases=(
                "amount",
                "sum",
                "value",
                "transaction_amount",
                "transactionAmount",
            ),
            transform=to_decimal_text,
            required=True,
        ),
        "currency": FieldMapping(
            aliases=("currency", "currencyCode", "ccy", "curr"),
            transform=to_upper_token,
            required=True,
        ),
        "direction": FieldMapping(
            aliases=(
                "direction",
                "transaction_type",
                "transactionType",
                "type",
                "drcr",
                "dr_cr",
                "credit_debit",
                "entryType",
            ),
            transform=normalize_direction,
            default="unknown",
        ),
        "status": FieldMapping(
            aliases=("status", "state", "transactionStatus"),
            transform=normalize_status,
        ),
        "description": FieldMapping(
            aliases=("description", "details", "narrative", "reason", "note"),
            transform=to_stripped_string,
        ),
        "created_at": FieldMapping(
            aliases=(
                "created_at",
                "createdAt",
                "date",
                "booking_date",
                "bookingDate",
                "value_date",
                "timestamp",
            ),
            transform=to_datetime_value,
        ),
    },
)


TRANSFER_MAPPING_V1 = EntityMapping(
    version=CANONICAL_MAPPING_VERSION,
    fields={
        "transfer_id": FieldMapping(
            aliases=("transfer_id", "transferId", "id"),
            transform=to_stripped_string,
        ),
        "from_account_id": FieldMapping(
            aliases=(
                "from_account_id",
                "fromAccountId",
                "source_account_id",
                "sourceAccountId",
                "debtor_account_id",
            ),
            transform=to_stripped_string,
            required=True,
        ),
        "to_account_id": FieldMapping(
            aliases=(
                "to_account_id",
                "toAccountId",
                "destination_account_id",
                "destinationAccountId",
                "creditor_account_id",
            ),
            transform=to_stripped_string,
        ),
        "to_iban": FieldMapping(
            aliases=(
                "to_iban",
                "toIban",
                "iban",
                "destination_iban",
                "destinationIban",
                "beneficiary_iban",
                "beneficiaryIban",
            ),
            transform=to_iban,
        ),
        "amount": FieldMapping(
            aliases=("amount", "sum", "value", "transferAmount"),
            transform=to_decimal_text,
            required=True,
        ),
        "currency": FieldMapping(
            aliases=("currency", "currencyCode", "ccy"),
            transform=to_upper_token,
            required=True,
        ),
        "status": FieldMapping(
            aliases=("status", "state", "transferStatus"),
            transform=normalize_status,
        ),
        "description": FieldMapping(
            aliases=("description", "reason", "details", "note"),
            transform=to_stripped_string,
        ),
        "created_at": FieldMapping(
            aliases=("created_at", "createdAt", "date", "initiated_at", "initiatedAt"),
            transform=to_datetime_value,
        ),
        "executed_at": FieldMapping(
            aliases=("executed_at", "executedAt", "completed_at", "completedAt"),
            transform=to_datetime_value,
        ),
    },
)


STATEMENT_MAPPING_V1 = EntityMapping(
    version=CANONICAL_MAPPING_VERSION,
    fields={
        "account_id": FieldMapping(
            aliases=(
                "account_id",
                "accountId",
                "account.id",
                "account.account_id",
                "account.accountId",
            ),
            transform=to_stripped_string,
            required=True,
        ),
        "currency": FieldMapping(
            aliases=(
                "currency",
                "currencyCode",
                "account.currency",
                "account.currencyCode",
            ),
            transform=to_upper_token,
            required=True,
        ),
        "created_from": FieldMapping(
            aliases=("created_from", "createdFrom", "date_from", "fromDate"),
            transform=to_datetime_value,
        ),
        "created_to": FieldMapping(
            aliases=("created_to", "createdTo", "date_to", "toDate"),
            transform=to_datetime_value,
        ),
        "opening_balance": FieldMapping(
            aliases=("opening_balance", "openingBalance", "summary.opening_balance"),
            transform=to_decimal_text,
        ),
        "closing_balance": FieldMapping(
            aliases=("closing_balance", "closingBalance", "summary.closing_balance"),
            transform=to_decimal_text,
        ),
        "total_credit": FieldMapping(
            aliases=(
                "total_credit",
                "totalCredit",
                "summary.total_credit",
                "summary.totalCredit",
                "summary.creditTotal",
            ),
            transform=to_decimal_text,
        ),
        "total_debit": FieldMapping(
            aliases=(
                "total_debit",
                "totalDebit",
                "summary.total_debit",
                "summary.totalDebit",
                "summary.debitTotal",
            ),
            transform=to_decimal_text,
        ),
        "total_count": FieldMapping(
            aliases=(
                "total_count",
                "totalCount",
                "summary.count",
                "summary.total_count",
                "summary.totalCount",
                "summary.totalItems",
            ),
            transform=to_int_value,
        ),
    },
)


STATEMENT_ITEMS_ALIASES = (
    "items",
    "transactions",
    "entries",
    "statementItems",
    "statement.items",
)


_MAPPING_BY_VERSION: dict[str, dict[str, EntityMapping]] = {
    CANONICAL_MAPPING_VERSION: {
        ENTITY_ACCOUNT: ACCOUNT_MAPPING_V1,
        ENTITY_TRANSACTION: TRANSACTION_MAPPING_V1,
        ENTITY_TRANSFER: TRANSFER_MAPPING_V1,
        ENTITY_STATEMENT: STATEMENT_MAPPING_V1,
    }
}


def get_entity_mapping(
    entity: str,
    *,
    version: str = CANONICAL_MAPPING_VERSION,
) -> EntityMapping:
    version_map = _MAPPING_BY_VERSION.get(str(version or "").strip())
    if version_map is None:
        raise KeyError(f"Unknown canonical mapping version: {version}")

    key = str(entity or "").strip().lower()
    mapping = version_map.get(key)
    if mapping is None:
        raise KeyError(f"Unknown canonical mapping entity: {entity}")
    return mapping
