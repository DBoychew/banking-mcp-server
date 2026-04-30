from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from banking_mcp.adapters.provider_adapter import (
    ProviderCapabilities,
    ProviderOperation,
)
from banking_mcp.core.circuit_breaker import NamedCircuitBreaker
from banking_mcp.config import settings

logger = logging.getLogger(__name__)


class EBankHTTPTools:
    """eBank HTTP adapter for MCP read-only account operations."""

    _SUPPORTED_OPERATIONS: frozenset[ProviderOperation] = frozenset(
        {
            "get_me",
            "list_accounts",
            "list_transactions",
            "get_statement",
        }
    )

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_s: Optional[float] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        language: Optional[str] = None,
        auth_mode: Optional[str] = None,
        session_ttl_s: Optional[int] = None,
    ) -> None:
        self.base_url = (base_url or settings.EBANK_BASE_URL).rstrip("/")
        self.timeout_s = (
            float(timeout_s)
            if timeout_s is not None
            else float(settings.EBANK_TIMEOUT_S)
        )
        self.username = str(
            username if username is not None else settings.EBANK_USERNAME
        ).strip()
        self.password = str(
            password if password is not None else settings.EBANK_PASSWORD
        ).strip()
        self.language = (
            str(language if language is not None else settings.EBANK_LANGUAGE).strip()
            or "BG"
        )
        self.auth_mode = self._normalize_auth_mode(
            auth_mode if auth_mode is not None else settings.EBANK_AUTH_MODE
        )
        self.session_ttl_s = int(
            session_ttl_s if session_ttl_s is not None else settings.EBANK_SESSION_TTL_S
        )

        self.login_path = self._normalize_path(settings.EBANK_LOGIN_PATH)
        self.home_path = self._normalize_path(settings.EBANK_HOME_PATH)
        self.enquiry_path = self._normalize_path(settings.EBANK_ENQUIRY_PATH)
        self.acclist_funcid = str(settings.EBANK_ACCLIST_FUNCID or "").strip()
        self.statement_funcid = str(settings.EBANK_STATEMENT_FUNCID or "").strip()

        self._client_lock = threading.Lock()
        self._client: Optional[httpx.AsyncClient] = None
        self._session_lock = asyncio.Lock()
        self._session: Optional[dict[str, str]] = None
        self._session_obj: Optional[dict[str, Any]] = None
        self._session_updated_at = 0.0
        self._circuit_breaker = NamedCircuitBreaker(
            enabled=bool(settings.MCP_UPSTREAM_CIRCUIT_BREAKER_ENABLED),
            failure_threshold=int(
                settings.MCP_UPSTREAM_CIRCUIT_BREAKER_FAILURE_THRESHOLD
            ),
            recovery_timeout_s=float(settings.MCP_UPSTREAM_CIRCUIT_BREAKER_RECOVERY_S),
            half_open_success_threshold=int(
                settings.MCP_UPSTREAM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD
            ),
        )

    @staticmethod
    def _normalize_path(path: str) -> str:
        token = str(path or "").strip()
        if not token:
            raise ValueError("eBank endpoint path cannot be empty.")
        if not token.startswith("/"):
            token = "/" + token
        return token

    @staticmethod
    def _normalize_auth_mode(value: Optional[str]) -> str:
        token = str(value or "").strip().lower()
        if not token:
            return "auto"
        if token not in {"auto", "service", "delegated"}:
            raise ValueError(
                "eBank auth mode must be one of: auto, service, delegated."
            )
        return token

    @staticmethod
    def _decode_base64url(raw: str) -> Optional[str]:
        token = str(raw or "").strip()
        if not token:
            return None
        token = token.replace("-", "+").replace("_", "/")
        missing_padding = len(token) % 4
        if missing_padding:
            token += "=" * (4 - missing_padding)
        try:
            return base64.b64decode(token).decode("utf-8")
        except Exception:
            return None

    @classmethod
    def _parse_basic_credentials(
        cls,
        authorization: Optional[str],
    ) -> Optional[tuple[str, str]]:
        raw = str(authorization or "").strip()
        if not raw:
            return None
        parts = raw.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "basic":
            return None
        decoded = cls._decode_base64url(parts[1])
        if not decoded or ":" not in decoded:
            return None
        username, password = decoded.split(":", 1)
        username = username.strip()
        password = password.strip()
        if not username or not password:
            return None
        return username, password

    @classmethod
    def _parse_ebank_session_payload(
        cls,
        token: str,
    ) -> Optional[dict[str, str]]:
        raw = str(token or "").strip()
        if not raw:
            return None

        payload_text: Optional[str]
        if raw.startswith("{"):
            payload_text = raw
        else:
            payload_text = cls._decode_base64url(raw)
        if not payload_text:
            return None
        try:
            payload = json.loads(payload_text)
        except Exception:
            return None
        if not isinstance(payload, Mapping):
            return None

        session = {
            "id": str(
                payload.get("sessid")
                or payload.get("sess")
                or payload.get("session_id")
                or payload.get("session")
                or payload.get("sessionid")
                or payload.get("user_sess")
                or payload.get("USER_SESS")
                or payload.get("id")
                or ""
            ).strip(),
            "lang": str(payload.get("lang") or payload.get("language") or "BG").strip()
            or "BG",
            "userid": str(
                payload.get("userid")
                or payload.get("user_id")
                or payload.get("user")
                or payload.get("username")
                or payload.get("USER_NAME")
                or payload.get("USER")
                or payload.get("usr")
                or payload.get("user")
                or ""
            ).strip(),
            "customerid": str(
                payload.get("customerid")
                or payload.get("customer_id")
                or payload.get("customer")
                or payload.get("custid")
                or payload.get("CUSTID")
                or payload.get("cust")
                or ""
            ).strip(),
        }
        if not session["id"]:
            return None
        return session

    @classmethod
    def _parse_authorization_session(
        cls,
        authorization: Optional[str],
    ) -> Optional[dict[str, str]]:
        raw = str(authorization or "").strip()
        if not raw:
            return None
        parts = raw.split(" ", 1)
        if len(parts) != 2:
            return None
        scheme, token = parts[0].lower(), parts[1].strip()
        if not token:
            return None

        if scheme == "ebanksession":
            return cls._parse_ebank_session_payload(token)

        if scheme == "bearer":
            marker = "ebank_session:"
            if token.lower().startswith(marker):
                return cls._parse_ebank_session_payload(token[len(marker) :].strip())
        return None

    @staticmethod
    def _extract_payload_errors(payload: Any, *, section: str) -> list[str]:
        if not isinstance(payload, Mapping):
            return []

        root = payload.get(section)
        roots: list[Mapping[str, Any]] = []
        if isinstance(root, list):
            for item in root:
                if isinstance(item, Mapping):
                    roots.append(item)
        elif isinstance(root, Mapping):
            roots.append(root)
        if not roots:
            return []

        parsed: list[str] = []
        for root_item in roots:
            errors = root_item.get("ERRORS")
            error_nodes: list[Mapping[str, Any]] = []
            if isinstance(errors, list):
                for item in errors:
                    if isinstance(item, Mapping):
                        error_nodes.append(item)
            elif isinstance(errors, Mapping):
                error_nodes.append(errors)

            for error_node in error_nodes:
                rows = error_node.get("ERROR")
                row_nodes: list[Mapping[str, Any]] = []
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, Mapping):
                            row_nodes.append(row)
                elif isinstance(rows, Mapping):
                    row_nodes.append(rows)

                for row in row_nodes:
                    content = row.get("content")
                    if (
                        isinstance(content, list)
                        and content
                        and isinstance(content[0], list)
                        and content[0]
                    ):
                        parsed.append(str(content[0][0]).strip())
                        continue
                    msg = str(row.get("msg") or "").strip()
                    if msg:
                        parsed.append(msg)

        return [item for item in parsed if item]

    @staticmethod
    def _decimal_text(value: Any) -> Optional[str]:
        raw = str(value or "").strip().replace(" ", "").replace(",", ".")
        if not raw:
            return None
        try:
            parsed = Decimal(raw)
        except InvalidOperation:
            return None
        return format(parsed, "f")

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, Mapping):
            return [value]
        return []

    @classmethod
    def _parse_datetime_token(cls, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())

        raw = str(value or "").strip()
        if not raw:
            return None

        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass

        for fmt in (
            "%d/%m/%Y %H:%M:%S",
            "%d.%m.%Y %H:%M:%S",
            "%d/%m/%Y",
            "%d.%m.%Y",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None

    @classmethod
    def _to_ebank_date(cls, value: Any) -> Optional[str]:
        parsed = cls._parse_datetime_token(value)
        if parsed is None:
            return None
        return parsed.strftime("%d/%m/%Y")

    @classmethod
    def _to_iso_date(cls, value: Any) -> Optional[str]:
        parsed = cls._parse_datetime_token(value)
        if parsed is None:
            return None
        return parsed.date().isoformat()

    @staticmethod
    def _normalize_direction_token(value: Any) -> str:
        token = str(value or "").strip().upper()
        if token == "D":
            return "debit"
        if token in {"K", "C"}:
            return "credit"
        return "unknown"

    @staticmethod
    def _compose_description(row: Mapping[str, Any]) -> str:
        parts: list[str] = []
        for key in ("trname", "contragent", "namekt", "rem_i", "rem_ii", "rem_iii"):
            token = str(row.get(key) or "").strip()
            if not token:
                continue
            if token in parts:
                continue
            parts.append(token)
        return " | ".join(parts)

    @staticmethod
    def _ci_get(payload: Mapping[str, Any], key: str) -> Any:
        if key in payload:
            return payload[key]
        wanted = str(key).strip().lower()
        for candidate, value in payload.items():
            if isinstance(candidate, str) and candidate.lower() == wanted:
                return value
        return None

    @classmethod
    def _first_non_empty(cls, payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = cls._ci_get(payload, key)
            token = str(value or "").strip()
            if token:
                return token
        return ""

    @classmethod
    def _extract_accounts_from_obj(cls, payload: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not isinstance(payload, Mapping):
            return rows

        direct_account = payload.get("ACCOUNT")
        if isinstance(direct_account, list):
            rows.extend(row for row in direct_account if isinstance(row, Mapping))

        nested_accounts = payload.get("ACCOUNTS")
        if isinstance(nested_accounts, Mapping):
            account_rows = nested_accounts.get("ACCOUNT")
            if isinstance(account_rows, list):
                rows.extend(row for row in account_rows if isinstance(row, Mapping))
        elif isinstance(nested_accounts, list) and nested_accounts:
            first = nested_accounts[0]
            if isinstance(first, Mapping):
                account_rows = first.get("ACCOUNT")
                if isinstance(account_rows, list):
                    rows.extend(row for row in account_rows if isinstance(row, Mapping))

        acclist = payload.get("ACCLISTFOR")
        if isinstance(acclist, list) and acclist:
            first = acclist[0]
            if isinstance(first, Mapping):
                account_rows = first.get("ACCOUNT")
                if isinstance(account_rows, list):
                    rows.extend(row for row in account_rows if isinstance(row, Mapping))

        all_accounts = payload.get("ALLACCOUNTS")
        if isinstance(all_accounts, list) and all_accounts:
            first = all_accounts[0]
            if isinstance(first, Mapping):
                account_rows = first.get("ACCOUNT")
                if isinstance(account_rows, list):
                    rows.extend(row for row in account_rows if isinstance(row, Mapping))

        enquiry = payload.get("ENQUIRY")
        if isinstance(enquiry, list) and enquiry and isinstance(enquiry[0], Mapping):
            rows.extend(cls._extract_accounts_from_obj(enquiry[0]))

        return [dict(row) for row in rows]

    @classmethod
    def _normalize_account_row(cls, row: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        account_id = cls._first_non_empty(
            row,
            (
                "account_id",
                "accountId",
                "accountid",
                "id",
                "iban",
            ),
        )
        if not account_id:
            return None

        currency = cls._first_non_empty(
            row,
            (
                "currency",
                "currencyCode",
                "curr",
                "currdt",
                "currkt",
                "ccy",
            ),
        ).upper()
        if not currency:
            return None

        raw_balance = cls._first_non_empty(
            row,
            (
                "balance",
                "available_balance",
                "availableBalance",
                "available",
                "availbal",
                "amount",
                "current_balance",
                "currentBalance",
            ),
        )
        balance = cls._decimal_text(raw_balance) or "0"

        iban = cls._first_non_empty(
            row, ("iban", "IBAN", "accountIban", "account_iban")
        )
        status = cls._first_non_empty(row, ("status", "state", "stateid")).lower()
        if not status:
            status = "active"

        normalized = dict(row)
        normalized["id"] = account_id
        normalized["account_id"] = account_id
        normalized["provider_account_id"] = account_id
        normalized["currency"] = currency
        normalized["balance"] = balance
        normalized["status"] = status
        if iban:
            normalized["iban"] = iban.replace(" ", "").upper()
        return normalized

    def _url(self, path: str) -> str:
        p = path if path.startswith("/") else "/" + path
        return f"{self.base_url}{p}"

    def _json_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/xml, text/xml, */*; q=0.01",
            "Accept-Language": "en",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _form_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _get_client(self) -> httpx.AsyncClient:
        with self._client_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=self.timeout_s)
            return self._client

    def _clear_session(self) -> None:
        self._session = None
        self._session_obj = None
        self._session_updated_at = 0.0

    def _service_credentials_configured(self) -> bool:
        return bool(
            str(self.username or "").strip() and str(self.password or "").strip()
        )

    def _can_fallback_to_service_session(self) -> bool:
        if self.auth_mode == "delegated":
            return False
        return self._service_credentials_configured()

    def _session_valid(self) -> bool:
        if self._session is None:
            return False
        if not str(self._session.get("id") or "").strip():
            return False
        age = max(0.0, time.monotonic() - float(self._session_updated_at))
        return age < float(self.session_ttl_s)

    @staticmethod
    def _is_circuit_failure(exc: Exception) -> bool:
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.RequestError):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = int(exc.response.status_code)
            return status_code == 429 or status_code >= 500
        return False

    async def _run_with_circuit(
        self,
        operation_key: str,
        run: Callable[[], Awaitable[httpx.Response]],
    ) -> httpx.Response:
        self._circuit_breaker.before_call(operation_key)
        try:
            result = await run()
            self._circuit_breaker.record_success(operation_key)
            return result
        except Exception as exc:
            if self._is_circuit_failure(exc):
                self._circuit_breaker.record_failure(operation_key)
            raise

    async def _login(
        self,
        *,
        username: str,
        password: str,
        language: str,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        if not username or not password:
            raise RuntimeError(
                "eBank credentials are not configured. Set provider credentials."
            )

        payload = {
            "LOGIN": {
                "USER_NAME": {"content": [username]},
                "USER_PASS": {"content": [password]},
                "USER_LANG": {"content": [language]},
            },
        }

        async def _send_login_request() -> httpx.Response:
            response = await self._get_client().post(
                self._url(self.login_path),
                json=payload,
                headers=self._json_headers(),
            )
            response.raise_for_status()
            return response

        response = await self._run_with_circuit(
            f"POST {self.login_path}",
            _send_login_request,
        )
        body = response.json()
        if not isinstance(body, Mapping):
            raise RuntimeError("Malformed eBank login payload: expected JSON object.")

        errors = self._extract_payload_errors(body, section="LOGIN")
        if errors:
            request = response.request
            synthetic = httpx.Response(
                401,
                request=request,
                json={"error": " ".join(errors)},
            )
            raise httpx.HTTPStatusError(
                f"eBank login failed: {', '.join(errors)}",
                request=request,
                response=synthetic,
            )

        sessions = body.get("SESSION")
        if (
            not isinstance(sessions, list)
            or not sessions
            or not isinstance(sessions[0], Mapping)
        ):
            raise RuntimeError("Malformed eBank login payload: missing SESSION[0].")

        session_obj = dict(sessions[0])
        session = {
            "id": str(session_obj.get("id") or "").strip(),
            "lang": str(session_obj.get("lang") or language).strip() or language,
            "userid": str(session_obj.get("userid") or "").strip(),
            "customerid": str(session_obj.get("customerid") or "").strip(),
        }
        if not session["id"]:
            raise RuntimeError(
                "Malformed eBank login payload: SESSION[0].id is missing."
            )

        return session, session_obj

    async def _ensure_service_session(
        self, *, force_refresh: bool = False
    ) -> dict[str, str]:
        if not force_refresh and self._session_valid():
            return dict(self._session or {})

        async with self._session_lock:
            if not force_refresh and self._session_valid():
                return dict(self._session or {})
            session, session_obj = await self._login(
                username=self.username,
                password=self.password,
                language=self.language,
            )
            self._session = session
            self._session_obj = session_obj
            self._session_updated_at = time.monotonic()
            return dict(session)

    async def _home_session_obj(
        self, session: Mapping[str, str]
    ) -> Optional[dict[str, Any]]:
        payload = {
            "Sess": str(session.get("id") or ""),
            "Lang": str(session.get("lang") or self.language),
            "Cust": str(session.get("customerid") or ""),
            "User": str(session.get("userid") or ""),
            "rettype": "application/json",
        }

        async def _send_home_request() -> httpx.Response:
            response = await self._get_client().post(
                self._url(self.home_path),
                content=urlencode(payload),
                headers=self._form_headers(),
            )
            response.raise_for_status()
            return response

        response = await self._run_with_circuit(
            f"POST {self.home_path}",
            _send_home_request,
        )
        body = response.json()
        if not isinstance(body, Mapping):
            raise RuntimeError("Malformed eBank home payload: expected JSON object.")

        errors = self._extract_payload_errors(body, section="LOGIN")
        if errors:
            request = response.request
            synthetic = httpx.Response(
                401,
                request=request,
                json={
                    "code": "PROVIDER_SESSION_INVALID",
                    "error": " ".join(errors),
                },
            )
            raise httpx.HTTPStatusError(
                f"eBank session is invalid: {', '.join(errors)}",
                request=request,
                response=synthetic,
            )

        sessions = body.get("SESSION")
        if (
            not isinstance(sessions, list)
            or not sessions
            or not isinstance(sessions[0], Mapping)
        ):
            return None
        return dict(sessions[0])

    async def _accounts_from_enquiry(
        self, session: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        if not self.acclist_funcid:
            return []
        payload = {
            "ENQUIRY": {
                "sessid": str(session.get("id") or ""),
                "lang": str(session.get("lang") or self.language),
                "ACCLISTFOR": {
                    "funcid": self.acclist_funcid,
                },
            }
        }

        async def _send_enquiry_request() -> httpx.Response:
            response = await self._get_client().post(
                self._url(self.enquiry_path),
                json=payload,
                headers=self._json_headers(),
            )
            response.raise_for_status()
            return response

        response = await self._run_with_circuit(
            f"POST {self.enquiry_path}",
            _send_enquiry_request,
        )
        body = response.json()
        return self._extract_accounts_from_obj(body)

    @classmethod
    def _extract_statement_blocks(cls, payload: Any) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        if not isinstance(payload, Mapping):
            return blocks

        for enquiry_row in cls._as_list(payload.get("ENQUIRY")):
            if not isinstance(enquiry_row, Mapping):
                continue
            for wrapper_row in cls._as_list(enquiry_row.get("SMTWRAPER")):
                if not isinstance(wrapper_row, Mapping):
                    continue
                for currency_row in cls._as_list(wrapper_row.get("CURRENCIES")):
                    if not isinstance(currency_row, Mapping):
                        continue
                    currency = cls._first_non_empty(
                        currency_row,
                        ("value", "currency", "curr"),
                    ).upper()
                    for statement_group in cls._as_list(currency_row.get("STATEMENTS")):
                        if not isinstance(statement_group, Mapping):
                            continue
                        block = dict(statement_group)
                        if currency and "value" not in block:
                            block["value"] = currency
                        blocks.append(block)
        return blocks

    @classmethod
    def _statement_block_for_account(
        cls, blocks: list[dict[str, Any]], account_id: Optional[str]
    ) -> Optional[dict[str, Any]]:
        if not blocks:
            return None
        account = str(account_id or "").strip()
        if not account:
            return dict(blocks[0])
        for block in blocks:
            candidate = cls._first_non_empty(
                block,
                ("account_id", "accountid", "id"),
            )
            if candidate == account:
                return dict(block)
        return None

    @classmethod
    def _signed_amount_from_row(cls, row: Mapping[str, Any]) -> Decimal:
        amount = Decimal(cls._decimal_text(row.get("amount")) or "0")
        direction = (
            str(row.get("direction") or row.get("transaction_type") or "")
            .strip()
            .lower()
        )
        if direction == "debit":
            return -abs(amount)
        if direction == "credit":
            return abs(amount)
        return amount

    @classmethod
    def _parse_balance_decimal(cls, value: Any) -> Optional[Decimal]:
        raw = cls._decimal_text(value)
        if raw is None:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None

    @classmethod
    def _fill_statement_balances(
        cls,
        *,
        rows: list[dict[str, Any]],
        opening_balance: Optional[Decimal],
        closing_balance: Optional[Decimal],
    ) -> None:
        if not rows:
            return

        order = sorted(
            range(len(rows)),
            key=lambda index: (
                cls._parse_datetime_token(rows[index].get("created_at"))
                or datetime.min,
                index,
            ),
        )

        balances: list[Optional[Decimal]] = []
        signed_amounts: list[Decimal] = []
        for row in rows:
            explicit_balance = cls._parse_balance_decimal(
                row.get("balance_after")
                or row.get("balance")
                or row.get("balanceafter")
            )
            balances.append(explicit_balance)
            signed_amounts.append(cls._signed_amount_from_row(row))

        if opening_balance is not None:
            running = opening_balance
            for index in order:
                if balances[index] is not None:
                    running = balances[index] or running
                    continue
                running = running + signed_amounts[index]
                balances[index] = running

        if closing_balance is not None:
            running = closing_balance
            for index in reversed(order):
                if balances[index] is not None:
                    running = balances[index] or running
                    continue
                balances[index] = running
                running = running - signed_amounts[index]

        for index, balance in enumerate(balances):
            if balance is None:
                continue
            rows[index]["balance_after"] = format(
                balance.quantize(Decimal("0.01")),
                "f",
            )

    @classmethod
    def _normalize_statement_transactions(
        cls, block: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        account_id = cls._first_non_empty(
            block,
            ("account_id", "accountid", "id"),
        )
        currency = cls._first_non_empty(
            block,
            ("currency", "value", "curr", "ccy"),
        ).upper()
        rows = cls._as_list(block.get("STATEMENT"))
        normalized: list[dict[str, Any]] = []
        for row_raw in rows:
            if not isinstance(row_raw, Mapping):
                continue
            row = dict(row_raw)
            created_at = cls._to_iso_date(
                row.get("datetime")
                or row.get("valuedate")
                or row.get("date")
                or row.get("created_at")
            )
            direction = cls._normalize_direction_token(
                row.get("dtkt") or row.get("direction")
            )
            amount = cls._decimal_text(row.get("amount")) or "0"
            transaction_id = cls._first_non_empty(
                row,
                ("transaction_id", "transactionid", "id", "reference"),
            )
            description = cls._compose_description(row)

            item = dict(row)
            if transaction_id:
                item["id"] = transaction_id
                item["transaction_id"] = transaction_id
            if account_id:
                item["account_id"] = account_id
            if currency:
                item["currency"] = currency
            item["amount"] = amount
            item["transaction_type"] = direction
            item["direction"] = direction
            if created_at:
                item["created_at"] = created_at
                item["date"] = created_at
            if description:
                item["description"] = description
            normalized.append(item)

        opening_balance = cls._parse_balance_decimal(
            block.get("balancestart") or block.get("opening_balance")
        )
        closing_balance = cls._parse_balance_decimal(
            block.get("balanceend") or block.get("closing_balance")
        )
        cls._fill_statement_balances(
            rows=normalized,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
        )
        return normalized

    @classmethod
    def _default_statement_date_range(
        cls,
        *,
        session: Mapping[str, str],
        args: Mapping[str, Any],
    ) -> tuple[str, str]:
        explicit_from = cls._to_ebank_date(args.get("created_from"))
        explicit_to = cls._to_ebank_date(args.get("created_to"))
        if explicit_from and explicit_to:
            return explicit_from, explicit_to

        anchor = (
            cls._parse_datetime_token(session.get("today"))
            or cls._parse_datetime_token(args.get("created_to"))
            or datetime.utcnow()
        )

        if explicit_from and not explicit_to:
            return explicit_from, anchor.strftime("%d/%m/%Y")

        if explicit_to and not explicit_from:
            start = explicit_to
            start_dt = cls._parse_datetime_token(start) or anchor
            from_dt = start_dt.replace(day=1)
            return from_dt.strftime("%d/%m/%Y"), explicit_to

        first_day = anchor.replace(day=1)
        return first_day.strftime("%d/%m/%Y"), anchor.strftime("%d/%m/%Y")

    @classmethod
    def _build_transactions_enquiry_payload(
        cls,
        *,
        session: Mapping[str, str],
        args: Mapping[str, Any],
        account_iban: Optional[str] = None,
        statement_funcid: Optional[str] = None,
    ) -> dict[str, Any]:
        statement_filter: dict[str, Any] = {
            "details": str(args.get("details") or "all").strip() or "all",
        }
        funcid = str(statement_funcid or "").strip()
        if funcid:
            statement_filter["funcid"] = funcid
        account_id = str(args.get("account_id") or "").strip()
        if account_id:
            statement_filter["accountid"] = account_id
        elif str(account_iban or "").strip():
            statement_filter["iban"] = str(account_iban or "").strip()

        created_from = cls._to_ebank_date(args.get("created_from"))
        created_to = cls._to_ebank_date(args.get("created_to"))
        if created_from:
            statement_filter["datefrom"] = created_from
        if created_to:
            statement_filter["dateto"] = created_to

        return {
            "ENQUIRY": {
                "sessid": str(session.get("id") or "").strip(),
                "lang": str(session.get("lang") or "BG").strip() or "BG",
                "SMTWRAPER": statement_filter,
            }
        }

    @staticmethod
    def _http_status_error_text(exc: httpx.HTTPStatusError) -> str:
        """Best-effort extraction of normalized provider error text."""
        try:
            payload = exc.response.json()
        except Exception:
            payload = exc.response.text or ""

        if isinstance(payload, Mapping):
            message = str(
                payload.get("error")
                or payload.get("detail")
                or payload.get("message")
                or ""
            ).strip()
            if message:
                return message.lower()
        return str(payload).strip().lower()

    @classmethod
    def _should_retry_statement_with_iban(
        cls,
        *,
        exc: httpx.HTTPStatusError,
        account_iban: Optional[str],
        query_args: Mapping[str, Any],
    ) -> bool:
        """Retry with IBAN only for explicit account-id/iban mismatch errors."""
        if exc.response.status_code != 400:
            return False
        if not account_iban or not query_args.get("account_id"):
            return False

        error_text = cls._http_status_error_text(exc)
        if not error_text:
            return False

        iban_retry_markers = (
            "erribandtnotallowed",
            "erribannotallowed",
            "iban",
            "accountid",
        )
        blocking_markers = (
            "errunauthorizedfunc",
            "unauthorizedfunc",
            "unauthorized",
            "forbidden",
            "notauthorized",
        )
        if any(marker in error_text for marker in blocking_markers):
            return False
        return any(marker in error_text for marker in iban_retry_markers)

    async def _account_statement_hints(
        self,
        *,
        authorization: Optional[str],
        account_id: str,
    ) -> tuple[Optional[str], Optional[str]]:
        if not account_id:
            return None, None
        try:
            accounts = await self._load_accounts(authorization)
        except Exception:
            logger.warning(
                "_load_accounts failed during account_id lookup", exc_info=True
            )
            raise
        for row in accounts:
            candidate = str(row.get("account_id") or row.get("id") or "").strip()
            if candidate != account_id:
                continue
            currency = str(row.get("currency") or "").strip().upper() or None
            iban = str(row.get("iban") or "").strip().upper() or None
            return currency, iban
        return None, None

    async def _request_statement_blocks(
        self,
        *,
        session: Mapping[str, str],
        args: Mapping[str, Any],
        authorization: Optional[str],
    ) -> list[dict[str, Any]]:
        query_args = dict(args or {})
        account_id = str(query_args.get("account_id") or "").strip()
        selected_account_row: Optional[dict[str, Any]] = None
        if not account_id:
            try:
                accounts = await self._load_accounts(authorization)
            except Exception:
                logger.warning(
                    "_load_accounts failed; cannot resolve account_id", exc_info=True
                )
                raise
            for row in accounts:
                candidate = str(row.get("account_id") or row.get("id") or "").strip()
                if candidate:
                    account_id = candidate
                    query_args["account_id"] = candidate
                    selected_account_row = row
                    break

        _, account_iban = await self._account_statement_hints(
            authorization=authorization,
            account_id=account_id,
        )
        if selected_account_row is not None:
            if not account_iban:
                account_iban = (
                    str(selected_account_row.get("iban") or "").strip().upper() or None
                )
        if not account_iban:
            account_iban = str(query_args.get("iban") or "").strip().upper() or None

        date_from, date_to = self._default_statement_date_range(
            session=session,
            args=query_args,
        )
        query_args["created_from"] = date_from
        query_args["created_to"] = date_to

        payload = self._build_transactions_enquiry_payload(
            session=session,
            args=query_args,
            account_iban=account_iban,
            statement_funcid=self.statement_funcid,
        )
        try:
            body = await self._enquiry_json(payload)
            return self._extract_statement_blocks(body)
        except httpx.HTTPStatusError as exc:
            should_retry_with_iban = self._should_retry_statement_with_iban(
                exc=exc,
                account_iban=account_iban,
                query_args=query_args,
            )
            if not should_retry_with_iban:
                raise

            fallback_args = dict(query_args)
            fallback_args.pop("account_id", None)
            fallback_args["iban"] = str(account_iban).strip().upper()
            fallback_payload = self._build_transactions_enquiry_payload(
                session=session,
                args=fallback_args,
                account_iban=account_iban,
                statement_funcid=self.statement_funcid,
            )
            body = await self._enquiry_json(fallback_payload)
            return self._extract_statement_blocks(body)

    async def _enquiry_json(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        async def _send_enquiry_request() -> httpx.Response:
            response = await self._get_client().post(
                self._url(self.enquiry_path),
                json=payload,
                headers=self._json_headers(),
            )
            response.raise_for_status()
            return response

        response = await self._run_with_circuit(
            f"POST {self.enquiry_path}",
            _send_enquiry_request,
        )
        body = response.json()
        if not isinstance(body, Mapping):
            raise RuntimeError("Malformed eBank enquiry payload: expected JSON object.")

        errors = self._extract_payload_errors(body, section="ENQUIRY")
        if not errors:
            errors = self._extract_payload_errors(body, section="LOGIN")
        if errors:
            lowered = " ".join(errors).lower()
            is_session_error = "errsessid" in lowered
            status_code = 401 if is_session_error else 400
            code = (
                "PROVIDER_SESSION_INVALID"
                if is_session_error
                else "PROVIDER_ENQUIRY_ERROR"
            )
            request = response.request
            synthetic = httpx.Response(
                status_code,
                request=request,
                json={"code": code, "error": " ".join(errors)},
            )
            raise httpx.HTTPStatusError(
                f"eBank enquiry failed: {', '.join(errors)}",
                request=request,
                response=synthetic,
            )
        return dict(body)

    async def _resolve_active_session(
        self,
        authorization: Optional[str],
    ) -> dict[str, str]:
        delegated_auth = (
            self._parse_authorization_session(authorization) is not None
            or self._parse_basic_credentials(authorization) is not None
        )
        mode, session, seed_session_obj = await self._resolve_auth_session(
            authorization
        )
        try:
            home_obj = await self._home_session_obj(session)
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code in {401, 403}
                and delegated_auth
                and self._can_fallback_to_service_session()
            ):
                self._clear_session()
                _, session, seed_session_obj = await self._resolve_auth_session(
                    None,
                    force_refresh=True,
                )
                home_obj = await self._home_session_obj(session)
                mode = "service"
            elif exc.response.status_code in {401, 403} and mode == "service":
                self._clear_session()
                _, session, seed_session_obj = await self._resolve_auth_session(
                    authorization,
                    force_refresh=True,
                )
                home_obj = await self._home_session_obj(session)
            else:
                raise

        source = dict(home_obj or seed_session_obj or {})
        active_session = {
            "id": str(source.get("id") or session.get("id") or "").strip(),
            "lang": str(
                source.get("lang") or session.get("lang") or self.language
            ).strip()
            or self.language,
            "userid": str(source.get("userid") or session.get("userid") or "").strip(),
            "customerid": str(
                source.get("customerid") or session.get("customerid") or ""
            ).strip(),
            "today": str(source.get("today") or "").strip(),
        }
        if not active_session["id"]:
            raise RuntimeError("eBank session id is missing for enquiry request.")

        if mode == "service" and home_obj:
            self._session = dict(active_session)
            self._session_obj = dict(source)
            self._session_updated_at = time.monotonic()

        return active_session

    def _raise_provider_auth_required(self) -> None:
        request = httpx.Request("POST", self._url(self.home_path))
        response = httpx.Response(
            401,
            request=request,
            json={
                "code": "PROVIDER_AUTH_REQUIRED",
                "detail": (
                    "Missing provider session. Send X-Provider-Authorization "
                    "with 'Basic <base64(user:pass)>' or "
                    "'EbankSession <base64url-json>'."
                ),
            },
        )
        raise httpx.HTTPStatusError(
            "Provider delegated auth is required for eBank adapter.",
            request=request,
            response=response,
        )

    async def _resolve_auth_session(
        self,
        authorization: Optional[str],
        *,
        force_refresh: bool = False,
    ) -> tuple[str, dict[str, str], Optional[dict[str, Any]]]:
        if self.auth_mode == "service":
            session = await self._ensure_service_session(force_refresh=force_refresh)
            return "service", session, dict(self._session_obj or {})

        session_from_auth = self._parse_authorization_session(authorization)
        if session_from_auth is not None:
            return "delegated_session", session_from_auth, None

        basic_credentials = self._parse_basic_credentials(authorization)
        if basic_credentials is not None:
            username, password = basic_credentials
            session, session_obj = await self._login(
                username=username,
                password=password,
                language=self.language,
            )
            return "delegated_basic", session, session_obj

        if self.auth_mode == "delegated":
            self._raise_provider_auth_required()

        session = await self._ensure_service_session(force_refresh=force_refresh)
        return "service", session, dict(self._session_obj or {})

    async def _load_accounts(
        self, authorization: Optional[str]
    ) -> list[dict[str, Any]]:
        mode, session, seed_session_obj = await self._resolve_auth_session(
            authorization
        )
        home_obj = await self._home_session_obj(session)
        merged_session = dict(home_obj or seed_session_obj or {})
        if mode == "service" and home_obj:
            self._session_obj = merged_session
            self._session = {
                "id": str(home_obj.get("id") or session.get("id") or "").strip(),
                "lang": str(
                    home_obj.get("lang") or session.get("lang") or self.language
                ).strip()
                or self.language,
                "userid": str(
                    home_obj.get("userid") or session.get("userid") or ""
                ).strip(),
                "customerid": str(
                    home_obj.get("customerid") or session.get("customerid") or ""
                ).strip(),
            }
            self._session_updated_at = time.monotonic()

        accounts = self._extract_accounts_from_obj(merged_session)
        if not accounts:
            accounts = await self._accounts_from_enquiry(session)

        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in accounts:
            item = self._normalize_account_row(row)
            if item is None:
                continue
            token = str(item.get("account_id") or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(item)
        return normalized

    async def aclose(self) -> None:
        client: Optional[httpx.AsyncClient] = None
        with self._client_lock:
            if self._client is not None:
                client = self._client
                self._client = None
        if client is not None:
            await client.aclose()

    def provider_name(self) -> str:
        return "ebank_http"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(operations=self._SUPPORTED_OPERATIONS)

    async def get_me(self, authorization: Optional[str]) -> Any:
        delegated_auth = (
            self._parse_authorization_session(authorization) is not None
            or self._parse_basic_credentials(authorization) is not None
        )
        mode, session, seed_session_obj = await self._resolve_auth_session(
            authorization
        )
        try:
            home_obj = await self._home_session_obj(session)
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code in {401, 403}
                and delegated_auth
                and self._can_fallback_to_service_session()
            ):
                self._clear_session()
                _, session, seed_session_obj = await self._resolve_auth_session(
                    None,
                    force_refresh=True,
                )
                home_obj = await self._home_session_obj(session)
                mode = "service"
            elif exc.response.status_code in {401, 403} and mode == "service":
                self._clear_session()
                _, session, seed_session_obj = await self._resolve_auth_session(
                    authorization,
                    force_refresh=True,
                )
                home_obj = await self._home_session_obj(session)
            else:
                raise

        source = home_obj or seed_session_obj or {}
        if mode == "service" and home_obj:
            self._session_obj = dict(home_obj)

        return {
            "id": str(source.get("userid") or source.get("customerid") or "").strip(),
            "provider": "ebank_http",
            "session_id": str(source.get("id") or session.get("id") or "").strip(),
            "user_id": str(source.get("userid") or session.get("userid") or "").strip(),
            "customer_id": str(
                source.get("customerid") or session.get("customerid") or ""
            ).strip(),
            "language": str(
                source.get("lang") or session.get("lang") or self.language
            ).strip()
            or self.language,
        }

    async def list_accounts(self, authorization: Optional[str]) -> Any:
        delegated_auth = (
            self._parse_authorization_session(authorization) is not None
            or self._parse_basic_credentials(authorization) is not None
        )
        try:
            return await self._load_accounts(authorization)
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code in {401, 403}
                and delegated_auth
                and self._can_fallback_to_service_session()
            ):
                self._clear_session()
                await self._ensure_service_session(force_refresh=True)
                return await self._load_accounts(None)
            if (
                exc.response.status_code in {401, 403}
                and not delegated_auth
                and self.auth_mode != "delegated"
            ):
                self._clear_session()
                await self._ensure_service_session(force_refresh=True)
                return await self._load_accounts(authorization)
            raise

    async def list_beneficiaries(self, authorization: Optional[str]) -> Any:
        _ = authorization
        raise NotImplementedError(
            "Beneficiaries endpoint is not implemented in current read-only phase."
        )

    async def get_fx_rates(self, authorization: Optional[str]) -> Any:
        _ = authorization
        raise NotImplementedError("FX rates are not supported by eBank adapter.")

    async def list_transactions(
        self, args: dict[str, Any], authorization: Optional[str]
    ) -> Any:
        query_args = dict(args or {})
        account_id = str(query_args.get("account_id") or "").strip()
        if not account_id:
            try:
                accounts = await self._load_accounts(authorization)
            except Exception:
                logger.warning(
                    "_load_accounts failed; cannot resolve account_id", exc_info=True
                )
                raise
            for row in accounts:
                account_id = str(row.get("account_id") or row.get("id") or "").strip()
                if account_id:
                    query_args["account_id"] = account_id
                    break
        else:
            query_args["account_id"] = account_id

        session = await self._resolve_active_session(authorization)
        blocks = await self._request_statement_blocks(
            session=session,
            args=query_args,
            authorization=authorization,
        )
        selected_block = self._statement_block_for_account(blocks, account_id)
        if selected_block is None:
            return []

        transactions = self._normalize_statement_transactions(selected_block)
        created_from = self._parse_datetime_token(query_args.get("created_from"))
        created_to = self._parse_datetime_token(query_args.get("created_to"))
        if created_from or created_to:
            filtered: list[dict[str, Any]] = []
            for item in transactions:
                created_at = self._parse_datetime_token(item.get("created_at"))
                if created_at is None:
                    continue
                if created_from and created_at < created_from:
                    continue
                if created_to and created_at > created_to:
                    continue
                filtered.append(item)
            transactions = filtered

        ascending = bool(query_args.get("ascending"))
        transactions.sort(
            key=lambda item: (
                self._parse_datetime_token(item.get("created_at")) or datetime.min,
                str(item.get("transaction_id") or item.get("id") or ""),
            ),
            reverse=not ascending,
        )

        try:
            offset = int(query_args.get("offset") or 0)
        except (TypeError, ValueError):
            offset = 0
        if offset < 0:
            offset = 0

        limit_raw = query_args.get("limit")
        try:
            limit = int(limit_raw) if limit_raw is not None else None
        except (TypeError, ValueError):
            limit = None
        if limit is not None and limit < 1:
            limit = None

        sliced = transactions[offset:]
        if limit is not None:
            sliced = sliced[:limit]
        return sliced

    async def list_transfers(
        self, args: dict[str, Any], authorization: Optional[str]
    ) -> Any:
        _ = args, authorization
        raise NotImplementedError("Transfers are not supported by eBank adapter.")

    async def get_transfer_by_id(
        self,
        args: dict[str, Any],
        authorization: Optional[str],
    ) -> Any:
        _ = args, authorization
        raise NotImplementedError(
            "Transfer details are not supported by eBank adapter."
        )

    async def get_statement(
        self, args: dict[str, Any], authorization: Optional[str]
    ) -> Any:
        query_args = dict(args or {})
        account_id = str(query_args.get("account_id") or "").strip()
        if not account_id:
            try:
                accounts = await self._load_accounts(authorization)
            except Exception:
                logger.warning(
                    "_load_accounts failed; cannot resolve account_id", exc_info=True
                )
                raise
            for row in accounts:
                account_id = str(row.get("account_id") or row.get("id") or "").strip()
                if account_id:
                    query_args["account_id"] = account_id
                    break
        if not account_id:
            raise RuntimeError("account_id is required for eBank statements.")

        if not query_args.get("created_from"):
            query_args["created_from"] = query_args.get("from_date")
        if not query_args.get("created_to"):
            query_args["created_to"] = query_args.get("to_date")

        session = await self._resolve_active_session(authorization)
        blocks = await self._request_statement_blocks(
            session=session,
            args=query_args,
            authorization=authorization,
        )
        selected_block = self._statement_block_for_account(blocks, account_id)
        if selected_block is None:
            return {
                "account": {"id": account_id, "currency": ""},
                "created_from": None,
                "created_to": None,
                "opening_balance": None,
                "closing_balance": None,
                "summary": {"total_credit": "0", "total_debit": "0", "count": 0},
                "items": [],
            }

        transactions = self._normalize_statement_transactions(selected_block)

        total_credit = Decimal("0")
        total_debit = Decimal("0")
        for row in transactions:
            amount = Decimal(self._decimal_text(row.get("amount")) or "0")
            if str(row.get("direction") or "").strip().lower() == "credit":
                total_credit += amount
            elif str(row.get("direction") or "").strip().lower() == "debit":
                total_debit += amount

        currency = self._first_non_empty(
            selected_block,
            ("currency", "value", "curr"),
        ).upper()
        opening_balance = self._decimal_text(
            selected_block.get("balancestart") or selected_block.get("opening_balance")
        )
        closing_balance = self._decimal_text(
            selected_block.get("balanceend") or selected_block.get("closing_balance")
        )
        created_from = (
            self._to_iso_date(selected_block.get("datefrom"))
            or self._to_iso_date(query_args.get("created_from"))
            or self._to_iso_date(query_args.get("from_date"))
        )
        created_to = (
            self._to_iso_date(selected_block.get("dateto"))
            or self._to_iso_date(query_args.get("created_to"))
            or self._to_iso_date(query_args.get("to_date"))
        )

        count_raw = selected_block.get("count")
        try:
            total_count = int(count_raw)
        except (TypeError, ValueError):
            total_count = len(transactions)

        return {
            "account": {"id": account_id, "currency": currency},
            "account_id": account_id,
            "currency": currency,
            "created_from": created_from,
            "created_to": created_to,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "summary": {
                "total_credit": format(total_credit.quantize(Decimal("0.01")), "f"),
                "total_debit": format(total_debit.quantize(Decimal("0.01")), "f"),
                "count": max(total_count, len(transactions)),
            },
            "items": transactions,
        }
