"""Convert 'Transaction Categories Iris Solutions v.1.1.xlsx' to JSON.

The source workbook has merged-cell hierarchical layout that pandas reads as
NaN-filled gaps. This script forward-fills the hierarchy, normalizes keywords,
and emits a flat list of leaf categories suitable for runtime lookup.

The target application serves Bulgarian customers only, so Greek-language
columns and Greek payroll patterns are filtered out at conversion time.

Run:
    python scripts/convert_transaction_categories.py \\
        --src "C:/Users/dimitar.k.boychev/Desktop/Transaction Categories Iris Solutions v.1.1.xlsx" \\
        --out banking_mcp/resources/data/transaction_categories.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd


SHEET_INCOMING = "Входящи"
SHEET_OUTGOING = "Изходящи"
SHEET_PATTERNS = "Sheet1"

# Column index map (positional - the file uses merged headers we ignore).
# Row 0 of each sheet is the secondary header; data starts at row 1.
COL_FULL_CODE = 0
COL_MAIN_CODE = 1
COL_MAIN_NAME = 2
COL_MAIN_DESC = 3
COL_PRIMARY_CODE = 4
COL_PRIMARY_NAME = 5
COL_PRIMARY_DESC = 6
COL_SUB1_CODE = 7
COL_SUB1_NAME = 8
COL_SUB1_DESC = 9
COL_SUB2_CODE = 10
COL_SUB2_NAME = 11
COL_SUB2_DESC = 12
# Only the 'Входящи' sheet has this:
COL_KEYWORDS_BG = 13


def _contains_greek(text: str) -> bool:
    """True if any Greek/Coptic codepoint is present."""
    return any(
        "Ͱ" <= ch <= "Ͽ" or "ἀ" <= ch <= "῿" for ch in text
    )


def _clean(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _split_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,;\n]+", raw)
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        kw = part.strip().strip(".").strip()
        if not kw:
            continue
        key = kw.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(kw)
    return out


# Captures the keyword list embedded in BG descriptions:
#   "В описанието се съдържа ключови думи като - X, Y, Z [и др./или ...]"
# The list ends at the first stop phrase or end of sentence.
_KEYWORDS_IN_DESC_RE = re.compile(
    r"ключови\s+думи\s+(?:като|като\s*:)\s*[-–—:]?\s*"
    r"(?P<list>.+?)"
    r"(?:\s+и\s+др\b|\s+и\s+имена\b|\s+или\s+плащ|\.\s|$)",
    re.IGNORECASE | re.DOTALL,
)


def _keywords_from_description(description: str | None) -> list[str]:
    """Extract inline keywords from outgoing-category descriptions.

    Outgoing entries in the source workbook do not have a dedicated keyword
    column. Instead, the seed keywords are embedded in the description as
    'ключови думи като - X, Y, Z'. This helper teases them out so Phase 3
    matching can use the same keyword index for both directions.
    """
    if not description:
        return []
    match = _KEYWORDS_IN_DESC_RE.search(description)
    if not match:
        return []
    return _split_keywords(match.group("list"))


def _parse_full_code(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 12:
        return None
    return digits


def _level_from_code(code: str) -> str:
    """Return 'main' | 'primary' | 'sub1' | 'sub2' based on which segment is non-zero last."""
    segs = [code[0:3], code[3:6], code[6:9], code[9:12]]
    if segs[3] != "000":
        return "sub2"
    if segs[2] != "000":
        return "sub1"
    if segs[1] != "000":
        return "primary"
    return "main"


def _parse_sheet(
    path: Path, sheet_name: str, direction: str, has_kw_column: bool
) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    df = df.iloc[2:]  # skip 2 header rows: top label row + secondary header row

    rows: list[dict] = []

    # Forward-fill state for each hierarchy level.
    state = {
        "main": {"code": None, "name": None, "desc": None},
        "primary": {"code": None, "name": None, "desc": None},
        "sub1": {"code": None, "name": None, "desc": None},
    }

    for _, row in df.iterrows():
        full_code = _parse_full_code(_clean(row.iloc[COL_FULL_CODE]))
        if not full_code:
            continue

        main_code = _clean(row.iloc[COL_MAIN_CODE])
        main_name = _clean(row.iloc[COL_MAIN_NAME])
        main_desc = _clean(row.iloc[COL_MAIN_DESC])
        if main_code:
            state["main"] = {"code": main_code, "name": main_name, "desc": main_desc}

        primary_code = _clean(row.iloc[COL_PRIMARY_CODE])
        primary_name = _clean(row.iloc[COL_PRIMARY_NAME])
        primary_desc = _clean(row.iloc[COL_PRIMARY_DESC])
        if primary_code:
            state["primary"] = {
                "code": primary_code,
                "name": primary_name,
                "desc": primary_desc,
            }

        sub1_code = _clean(row.iloc[COL_SUB1_CODE])
        sub1_name = _clean(row.iloc[COL_SUB1_NAME])
        sub1_desc = _clean(row.iloc[COL_SUB1_DESC])
        if sub1_code:
            state["sub1"] = {
                "code": sub1_code,
                "name": sub1_name,
                "desc": sub1_desc,
            }

        sub2_code = _clean(row.iloc[COL_SUB2_CODE])
        sub2_name = _clean(row.iloc[COL_SUB2_NAME])
        sub2_desc = _clean(row.iloc[COL_SUB2_DESC])

        kw_bg_raw = _clean(row.iloc[COL_KEYWORDS_BG]) if has_kw_column else None

        if has_kw_column:
            keywords_bg = _split_keywords(kw_bg_raw)
        else:
            # Outgoing: keywords are embedded in the description.
            keywords_bg = _keywords_from_description(sub2_desc)

        entry: dict = {
            "full_code": full_code,
            "direction": direction,
            "level": _level_from_code(full_code),
            "main_category": {
                "code": state["main"]["code"],
                "name": state["main"]["name"],
            },
            "primary_category": (
                {"code": state["primary"]["code"], "name": state["primary"]["name"]}
                if state["primary"]["code"]
                else None
            ),
            "sub_level_1": (
                {"code": state["sub1"]["code"], "name": state["sub1"]["name"]}
                if state["sub1"]["code"]
                else None
            ),
            "sub_level_2": (
                {"code": sub2_code, "name": sub2_name} if sub2_code else None
            ),
            "leaf_name": sub2_name
            or (state["sub1"]["name"] if state["sub1"]["code"] else None)
            or (state["primary"]["name"] if state["primary"]["code"] else None)
            or state["main"]["name"],
            "description": sub2_desc
            or (state["sub1"]["desc"] if state["sub1"]["code"] else None)
            or (state["primary"]["desc"] if state["primary"]["code"] else None)
            or state["main"]["desc"],
            "keywords_bg": keywords_bg,
        }
        rows.append(entry)

    return rows


def _parse_payroll_patterns(path: Path) -> list[dict]:
    """Bulgarian-only payroll patterns. Greek examples are filtered out."""
    df = pd.read_excel(path, sheet_name=SHEET_PATTERNS)
    out: list[dict] = []
    current_reason: str | None = None
    for _, row in df.iterrows():
        reason = _clean(row.get("Reason"))
        example = _clean(row.get("Example"))
        if reason and not _contains_greek(reason):
            current_reason = reason
        if not example or _contains_greek(example):
            continue
        if current_reason is None or _contains_greek(current_reason):
            continue
        out.append({"pattern_group": current_reason.replace("\xa0", " "), "example": example.replace("\xa0", " ")})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        required=True,
        type=Path,
        help="Path to the source .xlsx file.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output JSON path (will be overwritten).",
    )
    args = parser.parse_args(argv)

    if not args.src.exists():
        print(f"Source file not found: {args.src}", file=sys.stderr)
        return 1

    incoming = _parse_sheet(
        args.src, SHEET_INCOMING, direction="incoming", has_kw_column=True
    )
    outgoing = _parse_sheet(
        args.src, SHEET_OUTGOING, direction="outgoing", has_kw_column=False
    )
    patterns = _parse_payroll_patterns(args.src)

    payload = {
        "version": "1.1",
        "source_file": args.src.name,
        "standard": "IRIS PSD2Hub transaction classification",
        "locale": "bg_BG",
        "counts": {
            "incoming": len(incoming),
            "outgoing": len(outgoing),
            "payroll_patterns": len(patterns),
        },
        "categories": incoming + outgoing,
        "payroll_patterns": patterns,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Wrote {args.out} "
        f"(incoming={len(incoming)}, outgoing={len(outgoing)}, patterns={len(patterns)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
