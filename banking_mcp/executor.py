"""
Code Executor — RestrictedPython sandbox for safe code execution.

Mirrors petru's src/executor.py exactly, adapted for banking_mcp imports.
"""

import json
import re
import operator
import math
from typing import Any, Dict, TYPE_CHECKING

import pandas as pd
import numpy as np
from RestrictedPython import compile_restricted, safe_globals
from RestrictedPython.Guards import guarded_iter_unpack_sequence, guarded_unpack_sequence
from RestrictedPython.PrintCollector import PrintCollector

from .tools_api import BankingToolsAPI

if TYPE_CHECKING:
    from .db.manager import DatabaseManager


def _inplacevar(op_str: str, x, y):
    op_map = {
        "+=": operator.iadd, "-=": operator.isub, "*=": operator.imul,
        "/=": operator.itruediv, "//=": operator.ifloordiv, "%=": operator.imod,
        "**=": operator.ipow,
    }
    if op_str in op_map:
        return op_map[op_str](x, y)
    raise ValueError(f"Unsupported operator: {op_str}")


def _write_(obj):
    if isinstance(obj, (dict, list, set)):
        return obj
    return obj


class SafeJSON:
    @staticmethod
    def _default_serializer(obj):
        if hasattr(obj, "tolist") and hasattr(obj, "shape"):
            return obj.tolist()
        if hasattr(obj, "item"):
            return obj.item()
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)

    @staticmethod
    def dumps(obj, **kwargs):
        kwargs.setdefault("default", SafeJSON._default_serializer)
        return json.dumps(obj, **kwargs)

    @staticmethod
    def loads(s, **kwargs):
        return json.loads(s, **kwargs)


class CodeExecutor:
    """
    Secure Python code executor using RestrictedPython.

    The sandbox exposes a `tools` object (BankingToolsAPI) with:
      - tools.execute_sql_query(sql)          → pd.DataFrame
      - tools.execute_domain_query(name, **p) → pd.DataFrame
      - tools.get_accounts()                  → list[dict]
      - tools.get_transactions(account_id, from_date, to_date) → list[dict]
      - tools.get_fx_rates(currencies)        → list[dict]
      - tools.accounts_df()                   → pd.DataFrame
      - tools.transactions_df(account_id, ...) → pd.DataFrame
      - tools.fx_rates_df()                   → pd.DataFrame
    """

    def __init__(self, db_manager: "DatabaseManager", default_connection: str | None = None):
        self.tools_api = BankingToolsAPI(db_manager, default_connection)

    def _normalize_code(self, code: str) -> str:
        replacements = {
            "‑": "-", "‐": "-", "‒": "-", "–": "-", "—": "-",
            "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
        }
        for uc, ac in replacements.items():
            code = code.replace(uc, ac)
        return code

    def _fix_multiline_fstrings(self, code: str) -> str:
        lines = code.split("\n")
        fixed = []
        for line in lines:
            if ('f"' in line or "f'" in line) and "\\n" in line:
                line = re.sub(r'f"([^"]*\\n[^"]*)"', r'f"""\1"""', line)
                line = re.sub(r"f'([^']*\\n[^']*)'", r"f'''\1'''", line)
            fixed.append(line)
        return "\n".join(fixed)

    def execute(self, code: str) -> Dict[str, Any]:
        try:
            code = self._normalize_code(code)
            code = self._fix_multiline_fstrings(code)

            forbidden_imports = [
                "duckdb", "sqlite3", "psycopg", "mysql", "pymongo",
                "sqlalchemy", "subprocess", "os",
            ]
            for forbidden in forbidden_imports:
                if f"import {forbidden}" in code or f"from {forbidden}" in code:
                    return {
                        "success": False,
                        "error": (
                            f"Direct database/system imports are not allowed. "
                            f"Use the `tools` object instead.\n\n"
                            f"Examples:\n"
                            f"  df = tools.execute_sql_query('SELECT * FROM bank_branches')\n"
                            f"  accounts = tools.get_accounts()\n"
                            f"  txns = tools.get_transactions('ACC-001', '2026-01-01', '2026-04-30')\n"
                            f"  fx = tools.get_fx_rates('USD,EUR')\n\n"
                            f"NOT: import {forbidden}"
                        ),
                    }

            if "print(" in code and "result" not in code:
                code = code.rstrip() + "\nresult = printed"

            compile_result = compile_restricted(code, filename="<inline code>", mode="exec")

            if hasattr(compile_result, "errors") and compile_result.errors:
                return {"success": False, "error": f"Syntax Error: {compile_result.errors}"}

            byte_code = compile_result.code if hasattr(compile_result, "code") else compile_result

            restricted_builtins = safe_globals.copy()
            restricted_builtins.update({
                "__import__": __import__,
                "_getattr_": getattr,
                "_getitem_": lambda obj, index: obj[index],
                "_getiter_": iter,
                "_write_": _write_,
                "float": float, "int": int, "str": str, "bool": bool,
                "list": list, "dict": dict, "tuple": tuple, "set": set,
                "sum": sum, "len": len, "range": range, "enumerate": enumerate,
                "min": min, "max": max, "round": round, "sorted": sorted, "zip": zip,
                "abs": abs, "math": math,
                "hasattr": hasattr, "getattr": getattr, "isinstance": isinstance,
                "Exception": Exception, "ValueError": ValueError,
                "TypeError": TypeError, "KeyError": KeyError,
                "pd": pd, "pandas": pd,
                "np": np, "numpy": np,
                "_inplacevar_": _inplacevar,
            })

            restricted_globals = {
                "__builtins__": restricted_builtins,
                "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
                "_unpack_sequence_": guarded_unpack_sequence,
                "_write_": _write_,
                "_getiter_": iter,
                "_getitem_": lambda obj, index: obj[index],
                "json": SafeJSON,
                "tools": self.tools_api,
                "_print_": PrintCollector,
                "_getattr_": getattr,
                "__name__": "restricted_execution",
            }

            exec(byte_code, restricted_globals, restricted_globals)

            result = restricted_globals.get("result", None)
            printed_output = restricted_globals.get("printed", "")

            if result is None and printed_output:
                result = printed_output
            elif result is None:
                return {"success": False, "error": "Code executed but variable 'result' was not defined."}

            return {"success": True, "result": result, "logs": printed_output}

        except Exception as e:
            return {"success": False, "error": f"Runtime Error: {str(e)}"}
