from __future__ import annotations

from datetime import datetime
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional

import httpx


def _normalize_decimal_text(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    return raw.replace(",", ".")


def _normalize_bnb_date(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


def parse_bnb_fx_payload(xml_text: str) -> dict[str, Any]:
    payload = (xml_text or "").lstrip("﻿").strip()
    if not payload:
        raise RuntimeError("BNB FX payload is empty.")

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise RuntimeError("Failed to parse BNB FX XML payload.") from exc

    title: Optional[str] = None
    as_of: Optional[str] = None
    rates: list[dict[str, Any]] = []

    for row in root.findall(".//ROW"):
        code = str(row.findtext("CODE") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            if title is None:
                candidate_title = str(row.findtext("TITLE") or "").strip()
                title = candidate_title or title
            continue

        name = str(row.findtext("NAME_") or "").strip()
        rate_per_eur = _normalize_decimal_text(row.findtext("RATE"))
        eur_per_unit = _normalize_decimal_text(row.findtext("REVERSERATE"))
        row_date = _normalize_bnb_date(row.findtext("CURR_DATE"))
        if row_date and as_of is None:
            as_of = row_date

        rates.append(
            {
                "code": code,
                "name": name,
                "rate_per_eur": rate_per_eur,
                "eur_per_unit": eur_per_unit,
                "as_of": row_date,
            }
        )

    if not rates:
        raise RuntimeError("BNB FX payload does not contain currency rates.")

    rates.sort(key=lambda item: str(item.get("code") or ""))
    return {
        "provider": "bnb",
        "base_currency": "EUR",
        "as_of": as_of,
        "title": title,
        "rates": rates,
        "count": len(rates),
    }


def _is_circuit_failure(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = int(exc.response.status_code)
        return status_code == 429 or status_code >= 500
    return False


async def fetch_bnb_fx_rates(
    *,
    client: httpx.AsyncClient,
    url: str,
    timeout_s: float,
    circuit_breaker: Any | None = None,
) -> dict[str, Any]:
    operation_key = "GET bnb_fx_rates"
    if circuit_breaker is not None:
        circuit_breaker.before_call(operation_key)
    try:
        response = await client.get(
            url,
            timeout=timeout_s,
            headers={"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8"},
        )
        response.raise_for_status()
        parsed = parse_bnb_fx_payload(response.text)
        parsed["source_url"] = url
        if circuit_breaker is not None:
            circuit_breaker.record_success(operation_key)
        return parsed
    except Exception as exc:
        if circuit_breaker is not None and _is_circuit_failure(exc):
            circuit_breaker.record_failure(operation_key)
        raise
