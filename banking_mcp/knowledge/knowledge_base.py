from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeCard:
    """Represents a static assistant knowledge card."""

    id: str
    title: str
    body: str
    keywords: tuple[str, ...]


KNOWLEDGE_CARDS: tuple[KnowledgeCard, ...] = (
    KnowledgeCard(
        id="kb-statement",
        title="Statement & Period Filters",
        body=(
            "You can request statements and history for periods like: today, last_7_days, "
            "this_month, and last_month."
        ),
        keywords=(
            "statement",
            "transactions",
            "history",
            "period",
            "извлечение",
            "транзакции",
        ),
    ),
    KnowledgeCard(
        id="kb-supported-ops",
        title="Supported Banking Actions",
        body=(
            "Supported actions: list accounts, balances, transactions, transfers, "
            "statements, FX rates, and spending analysis."
        ),
        keywords=("help", "support", "can", "capabilities", "възможности", "какво"),
    ),
)


def retrieve_knowledge(query: str, limit: int = 2) -> list[KnowledgeCard]:
    """Return top matching knowledge cards for the given query."""
    q = (query or "").lower()
    if not q:
        return []

    scored: list[tuple[int, KnowledgeCard]] = []
    for card in KNOWLEDGE_CARDS:
        score = sum(1 for keyword in card.keywords if keyword in q)
        if score > 0:
            scored.append((score, card))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [card for _, card in scored[: max(0, limit)]]


def knowledge_to_text(cards: list[KnowledgeCard]) -> str:
    """Convert selected knowledge cards to compact context text."""
    if not cards:
        return "(none)"
    lines: list[str] = []
    for card in cards:
        lines.append(f"- {card.title}: {card.body}")
    return "\n".join(lines)
