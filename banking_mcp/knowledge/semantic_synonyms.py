from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class IntentPattern:
    intent: str
    patterns: tuple[str, ...]


_INTENT_PATTERNS: tuple[IntentPattern, ...] = (
    IntentPattern(
        intent="confirm",
        patterns=(
            r"\b(confirm|yes\s*,?\s*confirm|proceed|approve|ok)\b",
            r"\b(потвърди|потвърждавам)\b",
        ),
    ),
    IntentPattern(
        intent="cancel",
        patterns=(
            r"\b(cancel|abort|stop)\b",
            r"\b(отказ|откажи)\b",
        ),
    ),
    IntentPattern(
        intent="banking_help",
        patterns=(
            r"\b(how\s+to|how\s+do\s+i|how\s+can\s+i|help\s+me|guide\s+me|explain\s+how)\b.*\b(statement|transactions?|accounts?|balance|analysis|compare|anomal(?:y|ies)|forecast|chart|spending)\b",
            r"\b(как\s+да|как\s+мога|помощ|обясни)\b.*\b(извлечение|транзакции|сметки|баланс|анализ|сравнение|аномалии|прогноза|диаграма|разход)\b",
        ),
    ),
    IntentPattern(
        intent="get_bank_public_info",
        patterns=(
            r"\b(contact|contacts|phone|email|call\s+center|swift|branch(?:es)?|office(?:s)?|location(?:s)?|working\s+hours|opening\s+hours|management|directors?|executives?|ceo)\b",
            r"\b(контакт|контакти|телефон|имейл|клон|клонове|офис|офиси|локация|адрес|работно\s+време|ръководство|директор|директори|служител|служители)\b",
        ),
    ),
    IntentPattern(
        intent="get_fx_rates",
        patterns=(
            r"\b(fx|foreign\s+exchange|forex|exchange\s+rates?|currency\s+rates?|bnb\s+(?:fx|rates?))\b",
            r"\b\d+(?:[.,]\d+)?\s*[a-z]{3}\s+(?:to|into|in)\s+[a-z]{3}\b",
            r"\b(?:convert|conversion|exchange)\b.*\b(?:to|into)\b",
            r"\b(?:конвертирай|обмени|колко\s+ще\s+са)\b.*\b(?:към|в)\b",
            r"\b(валутн(?:и|ия)?\s+курс(?:ове)?|курс(?:ове)?\s+на\s+валути|бнб)\b",
        ),
    ),
    IntentPattern(
        intent="prepare_transfer",
        patterns=(
            r"\b(transfer|send|send\s+money|wire|remit|payment)\b",
            r"\b(преведи|превод|прехвърл\w*|изпрат\w*|прати)\b",
        ),
    ),
    IntentPattern(
        intent="list_beneficiaries",
        patterns=(
            r"\b(beneficiaries?|show\s+my\s+beneficiaries|recipient\s+list)\b",
            r"\b(бенефициент|бенефициенти)\b",
        ),
    ),
    IntentPattern(
        intent="list_accounts",
        patterns=(
            r"\b(accounts?|list\s+accounts|show\s+my\s+accounts)\b",
            r"\b(сметка|сметки)\b",
        ),
    ),
    IntentPattern(
        intent="get_balance",
        patterns=(
            r"\b(balance|funds|how\s+much\s+do\s+i\s+have)\b",
            r"\b(баланс|наличност|остатък)\b",
        ),
    ),
    IntentPattern(
        intent="list_transactions",
        patterns=(
            r"\b(transactions?|activity|movements)\b",
            r"\b(транзакции|движения)\b",
        ),
    ),
    IntentPattern(
        intent="list_transfers",
        patterns=(
            r"\b(transfers?\s+(history|list)|list\s+my\s+transfers)\b",
            r"\b(история\s+на\s+преводи|преводи\s+история)\b",
        ),
    ),
    IntentPattern(
        intent="get_statement",
        patterns=(
            r"\b(statement|bank\s*statement)\b",
            r"\b(извлечение|банково\s+извлечение)\b",
        ),
    ),
)


def iter_intent_patterns() -> Iterable[IntentPattern]:
    return _INTENT_PATTERNS


def resolve_intent_from_text(text: str) -> Optional[str]:
    t = (text or "").strip().lower()
    if not t:
        return None
    for rule in _INTENT_PATTERNS:
        for pattern in rule.patterns:
            if re.search(pattern, t, re.IGNORECASE):
                return rule.intent
    return None
