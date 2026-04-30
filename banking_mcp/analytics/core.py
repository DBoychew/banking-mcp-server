"""
Rule-based spending analytics for the banking MCP server.

No LLM required — categorisation and aggregation are purely data-driven.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any, Optional

from banking_mcp.knowledge.semantic_catalog import (
    SEMANTIC_CATEGORY_CATALOG,
    semantic_category_label,
)
from banking_mcp.normalization.merchant_normalization import (
    canonical_merchant_name,
    display_merchant_name,
)


def _parse_decimal(value: Any) -> Decimal:
    token = str(value or "").strip().replace(" ", "").replace("\xa0", "")
    if not token:
        return Decimal("0")
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        token = token.replace(",", ".")
    try:
        return Decimal(token)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _row_category(row: dict[str, Any]) -> Optional[str]:
    """Classify a single transaction row into a coarse semantic category."""
    description = str(
        row.get("description") or row.get("details") or row.get("contragent") or ""
    ).lower()
    tx_type = str(
        row.get("direction") or row.get("transaction_type") or row.get("type") or ""
    ).lower()

    for category, definition in SEMANTIC_CATEGORY_CATALOG.items():
        keywords = definition.get("keywords", set())
        if any(keyword in description for keyword in keywords):
            if category == "income" and tx_type not in {"credit", "k", "cr"}:
                continue
            return category
    return None


def _top_merchants(items: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    counter: Counter[str] = Counter()
    raw_labels: dict[str, str] = {}
    for row in items:
        description = str(
            row.get("description") or row.get("details") or row.get("contragent") or ""
        ).strip()
        if description:
            canonical = canonical_merchant_name(description) or description
            counter[canonical] += 1
            raw_labels.setdefault(
                canonical, display_merchant_name(description) or description
            )
    return [raw_labels.get(label, label) for label, _ in counter.most_common(limit)]


def analyze_spending(
    transactions: list[dict[str, Any]],
    *,
    currency: str = "",
) -> dict[str, Any]:
    """
    Analyse a list of canonical transactions and return a spending breakdown.

    Returns:
        {
            "categories": [{"category": str, "label": str, "total": str, "count": int}],
            "top_merchants": [str],
            "total_debit": str,
            "total_credit": str,
            "currency": str,
            "transaction_count": int,
            "anomaly_signals": [{"description": str, "amount": str, "reason": str}],
        }
    """
    debit_by_category: dict[str, Decimal] = {}
    count_by_category: dict[str, int] = {}
    debit_amounts: list[Decimal] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    anomaly_signals: list[dict[str, Any]] = []

    debit_rows = [
        row for row in transactions
        if str(row.get("direction") or "").lower() == "debit"
    ]

    for row in transactions:
        amount = _parse_decimal(row.get("amount", "0"))
        direction = str(row.get("direction") or "").lower()

        if direction == "credit":
            total_credit += amount
            continue

        if direction == "debit":
            total_debit += amount
            debit_amounts.append(amount)

            category = _row_category(row) or "other"
            debit_by_category[category] = debit_by_category.get(category, Decimal("0")) + amount
            count_by_category[category] = count_by_category.get(category, 0) + 1

    med = median(debit_amounts) if debit_amounts else Decimal("0")
    threshold = med * Decimal("3") if med > 0 else None

    for row in debit_rows:
        amount = _parse_decimal(row.get("amount", "0"))
        description = str(
            row.get("description") or row.get("details") or row.get("contragent") or ""
        ).strip()
        if threshold and amount > threshold:
            anomaly_signals.append(
                {
                    "description": description,
                    "amount": format(amount.quantize(Decimal("0.01")), "f"),
                    "currency": currency,
                    "reason": "unusually large amount",
                }
            )

    categories = sorted(
        [
            {
                "category": cat,
                "label": semantic_category_label(cat, is_bg=False),
                "total": format(total.quantize(Decimal("0.01")), "f"),
                "count": count_by_category.get(cat, 0),
            }
            for cat, total in debit_by_category.items()
        ],
        key=lambda item: Decimal(item["total"]),
        reverse=True,
    )

    return {
        "categories": categories,
        "top_merchants": _top_merchants(transactions),
        "total_debit": format(total_debit.quantize(Decimal("0.01")), "f"),
        "total_credit": format(total_credit.quantize(Decimal("0.01")), "f"),
        "currency": currency,
        "transaction_count": len(transactions),
        "anomaly_signals": anomaly_signals[:10],
    }
