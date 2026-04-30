from __future__ import annotations

from typing import Any, Optional

from banking_mcp.canonical.mapping import (
    ENTITY_ACCOUNT,
    ENTITY_STATEMENT,
    ENTITY_TRANSACTION,
    ENTITY_TRANSFER,
    MISSING,
    STATEMENT_ITEMS_ALIASES,
    get_entity_mapping,
    is_missing_value,
    map_entity_fields,
    resolve_first_alias,
)
from banking_mcp.canonical.models import (
    CanonicalAccount,
    CanonicalStatement,
    CanonicalTransaction,
    CanonicalTransfer,
)

_ACCOUNT_MAPPING = get_entity_mapping(ENTITY_ACCOUNT)
_TRANSACTION_MAPPING = get_entity_mapping(ENTITY_TRANSACTION)
_TRANSFER_MAPPING = get_entity_mapping(ENTITY_TRANSFER)
_STATEMENT_MAPPING = get_entity_mapping(ENTITY_STATEMENT)


def canonical_account_from_any(value: Any) -> Optional[CanonicalAccount]:
    if isinstance(value, CanonicalAccount):
        return value

    mapped = map_entity_fields(value, _ACCOUNT_MAPPING)
    if mapped is None:
        return None

    if is_missing_value(mapped.get("provider_account_id")):
        provider_id = resolve_first_alias(value, ("id", "account.id"))
        if provider_id is not MISSING and not is_missing_value(provider_id):
            mapped["provider_account_id"] = str(provider_id).strip()

    try:
        return CanonicalAccount(**mapped)
    except Exception:
        return None


def canonical_transaction_from_any(value: Any) -> Optional[CanonicalTransaction]:
    if isinstance(value, CanonicalTransaction):
        return value

    mapped = map_entity_fields(value, _TRANSACTION_MAPPING)
    if mapped is None:
        return None

    try:
        return CanonicalTransaction(**mapped)
    except Exception:
        return None


def canonical_transfer_from_any(value: Any) -> Optional[CanonicalTransfer]:
    if isinstance(value, CanonicalTransfer):
        return value

    mapped = map_entity_fields(value, _TRANSFER_MAPPING)
    if mapped is None:
        return None

    to_account_id = mapped.get("to_account_id")
    to_iban = mapped.get("to_iban")
    if to_account_id and to_iban:
        # Canonical model enforces exactly one destination. Keep external target.
        mapped["to_account_id"] = None
    elif not to_account_id and not to_iban:
        return None

    try:
        return CanonicalTransfer(**mapped)
    except Exception:
        return None


def canonical_statement_from_any(value: Any) -> Optional[CanonicalStatement]:
    if isinstance(value, CanonicalStatement):
        return value

    mapped = map_entity_fields(value, _STATEMENT_MAPPING)
    if mapped is None:
        return None

    statement_account_id = str(mapped.get("account_id"))
    items_raw = resolve_first_alias(value, STATEMENT_ITEMS_ALIASES)
    item_rows = items_raw if isinstance(items_raw, list) else []
    items: list[CanonicalTransaction] = []
    for row in item_rows:
        item = canonical_transaction_from_any(row)
        if item is None:
            continue
        if not item.account_id:
            item = item.model_copy(update={"account_id": statement_account_id.strip()})
        items.append(item)

    total_count = mapped.get("total_count")
    if total_count is None:
        total_count = len(items)
    mapped["total_count"] = total_count

    try:
        return CanonicalStatement(**mapped, items=items)
    except Exception:
        return None


def canonical_accounts(values: Any) -> list[CanonicalAccount]:
    rows = values if isinstance(values, list) else []
    parsed: list[CanonicalAccount] = []
    for row in rows:
        item = canonical_account_from_any(row)
        if item is not None:
            parsed.append(item)
    return parsed


def canonical_transactions(values: Any) -> list[CanonicalTransaction]:
    rows = values if isinstance(values, list) else []
    parsed: list[CanonicalTransaction] = []
    for row in rows:
        item = canonical_transaction_from_any(row)
        if item is not None:
            parsed.append(item)
    return parsed


def canonical_transfers(values: Any) -> list[CanonicalTransfer]:
    rows = values if isinstance(values, list) else []
    parsed: list[CanonicalTransfer] = []
    for row in rows:
        item = canonical_transfer_from_any(row)
        if item is not None:
            parsed.append(item)
    return parsed
