from __future__ import annotations

import re
from typing import Any


HELP_TOPICS: tuple[str, ...] = (
    "accounts_balance",
    "transactions",
    "statement",
    "analytics",
    "anomalies",
    "forecast",
    "charts",
    "general",
)
HELP_LANGUAGES: tuple[str, ...] = ("en", "bg")

_TOPIC_ALIASES: dict[str, str] = {
    "accounts": "accounts_balance",
    "account": "accounts_balance",
    "balance": "accounts_balance",
    "balances": "accounts_balance",
    "accounts_balance": "accounts_balance",
    "transactions": "transactions",
    "history": "transactions",
    "activity": "transactions",
    "movements": "transactions",
    "statement": "statement",
    "statements": "statement",
    "analytics": "analytics",
    "analysis": "analytics",
    "insights": "analytics",
    "compare": "analytics",
    "comparison": "analytics",
    "categories": "analytics",
    "category": "analytics",
    "anomaly": "anomalies",
    "anomalies": "anomalies",
    "outlier": "anomalies",
    "forecast": "forecast",
    "projection": "forecast",
    "predict": "forecast",
    "chart": "charts",
    "charts": "charts",
    "diagram": "charts",
    "graph": "charts",
    "general": "general",
    "help": "general",
}

_LANGUAGE_ALIASES: dict[str, str] = {
    "en": "en",
    "en-us": "en",
    "en_us": "en",
    "english": "en",
    "bg": "bg",
    "bg-bg": "bg",
    "bg_bg": "bg",
    "bulgarian": "bg",
}

_TOPIC_HINTS: dict[str, tuple[str, ...]] = {
    "accounts_balance": (
        "show my accounts",
        "accounts",
        "account",
        "balance",
        "balances",
        "how much do i have",
        "сметки",
        "сметка",
        "баланс",
        "баланси",
        "колко пари имам",
    ),
    "transactions": (
        "transactions",
        "history",
        "movements",
        "merchant",
        "counterparty",
        "last transaction",
        "транзакции",
        "история",
        "движения",
        "последна транзакция",
        "плащане",
    ),
    "statement": (
        "statement",
        "bank statement",
        "account statement",
        "извлечение",
        "банково извлечение",
        "период",
    ),
    "analytics": (
        "top category",
        "top merchant",
        "where did i spend",
        "compare",
        "comparison",
        "spending analysis",
        "save the most",
        "food or fuel",
        "compare",
        "comparing",
        "срав",
        "сравня",
        "категория",
        "категории",
        "къде съм харчил",
        "сравни",
        "анализ",
        "какво да намаля",
    ),
    "anomalies": (
        "anomaly",
        "anomalies",
        "outlier",
        "unusual",
        "аномалия",
        "аномалии",
        "необичайно",
    ),
    "forecast": (
        "forecast",
        "projection",
        "predict",
        "by the end of the month",
        "by the end of the year",
        "прогноза",
        "очаква",
        "до края на месеца",
        "до края на годината",
    ),
    "charts": (
        "chart",
        "charts",
        "graph",
        "diagram",
        "диаграма",
        "графика",
        "графика за",
    ),
    "general": (
        "help",
        "what can you do",
        "how can you help",
        "support",
        "какво можеш да правиш",
        "как можеш да помогнеш",
        "помощ",
    ),
}

_TOPIC_CONTENT: dict[str, dict[str, dict[str, Any]]] = {
    "accounts_balance": {
        "en": {
            "message": (
                "You can ask for accounts and balances in natural language.\n"
                "Examples:\n"
                '- "show my accounts"\n'
                '- "show my balances"\n'
                '- "which account has more money"\n'
                '- "balance for account 1"\n\n'
                "If you pick an active account, the next balance and history questions will use it automatically."
            ),
            "suggested_prompts": [
                "show my accounts",
                "show my balances",
                "which account has more money",
            ],
        },
        "bg": {
            "message": (
                "Можеш да питаш за сметки и баланси на естествен език.\n"
                "Примери:\n"
                '- "покажи ми сметките"\n'
                '- "покажи ми балансите"\n'
                '- "коя сметка има повече пари"\n'
                '- "баланс за сметка 1"\n\n'
                "Ако избереш активна сметка, следващите въпроси за баланс и история ще я използват автоматично."
            ),
            "suggested_prompts": [
                "покажи ми сметките",
                "покажи ми балансите",
                "коя сметка има повече пари",
            ],
        },
    },
    "transactions": {
        "en": {
            "message": (
                "You can search transactions by period, merchant, category, amount, or account.\n"
                "Examples:\n"
                '- "show my transactions from last month"\n'
                '- "when was my last fuel transaction"\n'
                '- "show only OMV transactions from last year"\n'
                '- "transactions above 200 EUR"\n\n'
                "Follow-ups also work, for example: 'only OMV', 'and for last year', or 'show the details'."
            ),
            "suggested_prompts": [
                "show my transactions from last month",
                "when was my last fuel transaction",
                "show only OMV transactions from last year",
            ],
        },
        "bg": {
            "message": (
                "Можеш да търсиш транзакции по период, търговец, категория, сума или сметка.\n"
                "Примери:\n"
                '- "покажи ми транзакциите за миналия месец"\n'
                '- "кога е последната транзакция за гориво"\n'
                '- "покажи само OMV транзакциите от миналата година"\n'
                '- "транзакции над 200 евро"\n\n'
                "Работят и follow-up заявки като „само OMV", „а за миналата година" или „покажи детайлите"."
            ),
            "suggested_prompts": [
                "покажи ми транзакциите за миналия месец",
                "кога е последната транзакция за гориво",
                "покажи само OMV транзакциите от миналата година",
            ],
        },
    },
    "statement": {
        "en": {
            "message": (
                "Statements are for detailed account cashflow in a selected period.\n"
                "Examples:\n"
                '- "statement for account 1"\n'
                '- "statement for last month"\n'
                '- "statement from 2026-03-01 to 2026-03-31"\n\n'
                "The statement view supports filtering, sorting, pagination, charts, and date range selection."
            ),
            "suggested_prompts": [
                "statement for account 1",
                "statement for last month",
                "statement from 2026-03-01 to 2026-03-31",
            ],
        },
        "bg": {
            "message": (
                "Извлечението е за детайлна история по сметка за избран период.\n"
                "Примери:\n"
                '- "извлечение за сметка 1"\n'
                '- "извлечение за миналия месец"\n'
                '- "извлечение от 2026-03-01 до 2026-03-31"\n\n'
                "Изгледът на извлечението поддържа филтриране, сортиране, пагинация, графики и избор на период."
            ),
            "suggested_prompts": [
                "извлечение за сметка 1",
                "извлечение за миналия месец",
                "извлечение от 2026-03-01 до 2026-03-31",
            ],
        },
    },
    "analytics": {
        "en": {
            "message": (
                "You can ask for spending analysis by category, merchant, account, or period.\n"
                "Examples:\n"
                '- "what did I spend the most on last year"\n'
                '- "compare food and fuel for last year"\n'
                '- "where did I spend the most money"\n'
                '- "which expense should I reduce"\n\n'
                "The assistant can also explain the last shown recommendation or comparison."
            ),
            "suggested_prompts": [
                "what did I spend the most on last year",
                "compare food and fuel for last year",
                "which expense should I reduce",
            ],
        },
        "bg": {
            "message": (
                "Можеш да искаш анализ на разходите по категория, търговец, сметка или период.\n"
                "Примери:\n"
                '- "за какво съм харчил най-много пари миналата година"\n'
                '- "сравни ми храна и гориво за миналата година"\n'
                '- "къде съм харчил най-много пари"\n'
                '- "кой разход трябва да намаля"\n\n'
                "Асистентът може и да обясни последната показана препоръка или сравнение."
            ),
            "suggested_prompts": [
                "за какво съм харчил най-много пари миналата година",
                "сравни ми храна и гориво за миналата година",
                "кой разход трябва да намаля",
            ],
        },
    },
    "anomalies": {
        "en": {
            "message": (
                "Anomaly analysis highlights unusually large, rare, or new-looking spending patterns.\n"
                "Examples:\n"
                '- "show anomalies for the last 5 years"\n'
                '- "show anomalies for this year"\n'
                '- "why are these anomalies"\n\n'
                "After anomaly results are shown, you can ask a short follow-up like 'why' or 'explain them'."
            ),
            "suggested_prompts": [
                "show anomalies for the last 5 years",
                "show anomalies for this year",
                "why are these anomalies",
            ],
        },
        "bg": {
            "message": (
                "Анализът на аномалии откроява необичайно големи, редки или нови разходи.\n"
                "Примери:\n"
                '- "покажи ми аномалии за последните 5 години"\n'
                '- "покажи ми аномалии за тази година"\n'
                '- "защо са аномалии"\n\n'
                "След като покажа резултата, можеш да питаш кратко „защо" или „обясни ги"."
            ),
            "suggested_prompts": [
                "покажи ми аномалии за последните 5 години",
                "покажи ми аномалии за тази година",
                "защо са аномалии",
            ],
        },
    },
    "forecast": {
        "en": {
            "message": (
                "Forecasts estimate future spending based on the selected category and recent pace.\n"
                "Examples:\n"
                '- "forecast fuel spending until the end of the year"\n'
                '- "how much am I expected to spend on food by the end of the month"\n'
                '- "if I continue like this, how much will I spend on utilities"\n\n'
                "For better accuracy, mention a category and a target period."
            ),
            "suggested_prompts": [
                "forecast fuel spending until the end of the year",
                "how much am I expected to spend on food by the end of the month",
                "if I continue like this, how much will I spend on utilities",
            ],
        },
        "bg": {
            "message": (
                "Прогнозите оценяват бъдещ разход според избраната категория и текущото темпо.\n"
                "Примери:\n"
                '- "прогнозирай ми разхода за гориво до края на годината"\n'
                '- "колко се очаква да похарча за храна до края на месеца"\n'
                '- "ако продължавам така, колко ще дам за битови сметки"\n\n'
                "За по-точен резултат е добре да посочиш категория и целеви период."
            ),
            "suggested_prompts": [
                "прогнозирай ми разхода за гориво до края на годината",
                "колко се очаква да похарча за храна до края на месеца",
                "ако продължавам така, колко ще дам за битови сметки",
            ],
        },
    },
    "charts": {
        "en": {
            "message": (
                "You can ask for chart-ready summaries by period or category.\n"
                "Examples:\n"
                '- "show me a chart for the last 5 years"\n'
                '- "show a chart of what I spent the most on"\n'
                '- "show a chart for food and fuel"\n\n'
                "Charts work best when you mention a period, a category set, or a comparison target."
            ),
            "suggested_prompts": [
                "show me a chart for the last 5 years",
                "show a chart of what I spent the most on",
                "show a chart for food and fuel",
            ],
        },
        "bg": {
            "message": (
                "Можеш да искаш обобщения, готови за диаграма, по период или категория.\n"
                "Примери:\n"
                '- "изкарай ми диаграма за последните 5 години"\n'
                '- "изкарай ми диаграма за какво съм харчил най-много"\n'
                '- "покажи диаграма за храна и гориво"\n\n'
                "Диаграмите работят най-добре, когато зададеш период, категории или ясна посока за сравнение."
            ),
            "suggested_prompts": [
                "изкарай ми диаграма за последните 5 години",
                "изкарай ми диаграма за какво съм харчил най-много",
                "покажи диаграма за храна и гориво",
            ],
        },
    },
    "general": {
        "en": {
            "message": (
                "I can help with:\n"
                "- accounts and balances\n"
                "- transaction history and statements\n"
                "- spending analysis by category, merchant, and period\n"
                "- comparisons, anomalies, forecasts, and charts\n"
                "- account context selection for follow-up questions\n\n"
                "Examples:\n"
                '- "show my accounts"\n'
                '- "how much did I spend on fuel last year"\n'
                '- "compare food and fuel"\n'
                '- "show anomalies for the last 5 years"'
            ),
            "suggested_prompts": [
                "show my accounts",
                "how much did I spend on fuel last year",
                "compare food and fuel",
            ],
        },
        "bg": {
            "message": (
                "Мога да помогна със:\n"
                "- сметки и баланси\n"
                "- история на транзакции и извлечения\n"
                "- анализ на разходи по категория, търговец и период\n"
                "- сравнения, аномалии, прогнози и диаграми\n"
                "- избор на контекст на сметка за follow-up въпроси\n\n"
                "Примери:\n"
                '- "покажи ми сметките"\n'
                '- "колко съм дал за гориво миналата година"\n'
                '- "сравни ми храна и гориво"\n'
                '- "покажи ми аномалии за последните 5 години"'
            ),
            "suggested_prompts": [
                "покажи ми сметките",
                "колко съм дал за гориво миналата година",
                "сравни ми храна и гориво",
            ],
        },
    },
}

_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def normalize_help_topic(topic: str | None) -> str | None:
    if topic is None:
        return None
    normalized = _normalize(topic).replace(" ", "_")
    if normalized in HELP_TOPICS:
        return normalized
    return _TOPIC_ALIASES.get(normalized)


def normalize_help_language(language: str | None) -> str | None:
    if language is None:
        return None
    normalized = _normalize(language).replace("_", "-")
    return _LANGUAGE_ALIASES.get(normalized)


def infer_help_topic(question: str) -> str:
    q = _normalize(question)
    if not q:
        return "general"

    scores: dict[str, int] = {topic: 0 for topic in HELP_TOPICS}
    for topic, hints in _TOPIC_HINTS.items():
        scores[topic] = sum(1 for hint in hints if hint in q)

    winner = max(scores, key=scores.get)
    if scores[winner] <= 0:
        return "general"
    return winner


def infer_help_language(*, question: str, language: str | None = None) -> str:
    explicit = normalize_help_language(language)
    if explicit in HELP_LANGUAGES:
        return explicit
    if _CYRILLIC_RE.search(str(question or "")):
        return "bg"
    return "en"


def build_banking_help_payload(
    *,
    question: str = "",
    topic: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    resolved_topic = normalize_help_topic(topic) or infer_help_topic(question)
    resolved_language = infer_help_language(question=question, language=language)
    topic_content = _TOPIC_CONTENT.get(resolved_topic, _TOPIC_CONTENT["general"])
    localized = topic_content.get(resolved_language) or topic_content["en"]
    return {
        "topic": resolved_topic,
        "language": resolved_language,
        "message": str(localized.get("message") or ""),
        "suggested_prompts": list(localized.get("suggested_prompts") or []),
        "available_topics": list(HELP_TOPICS),
        "question": str(question or "").strip(),
    }
