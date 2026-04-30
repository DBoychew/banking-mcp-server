from __future__ import annotations

from typing import Any, Optional


_CONTACT_URL = "https://www.allianz.bg/bg_BG/individuals/get-in-touch.html"
_OFFICES_URL = "https://www.allianz.bg/bg_BG/individuals/banking/bank-offices-abb.html"
_BRANCH_EMAILS_URL = (
    "https://www.allianz.bg/content/dam/onemarketing/cee/azbg/bank/moratorium/"
    "ListBranchesEmails.pdf"
)


def _is_bg_language(language: Optional[str]) -> bool:
    """Return True if the language code indicates Bulgarian."""
    token = str(language or "").strip().lower()
    return token.startswith("bg")


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def infer_bank_knowledge_topic(question: str) -> Optional[str]:
    normalized = _normalize(question)
    if not normalized:
        return None

    if any(
        token in normalized
        for token in (
            "working hours",
            "opening hours",
            "open today",
            "hours",
            "работно време",
            "работното време",
            "часове",
            "отворено",
        )
    ):
        return "hours"

    if any(
        token in normalized
        for token in (
            "branch",
            "branches",
            "office",
            "offices",
            "location",
            "locations",
            "address",
            "клон",
            "клонове",
            "офис",
            "офиси",
            "локация",
            "локации",
            "адрес",
            "къде",
        )
    ):
        return "branches"

    if any(
        token in normalized
        for token in (
            "contact",
            "contacts",
            "phone",
            "email",
            "mail",
            "call center",
            "support",
            "contact us",
            "контакт",
            "контакти",
            "телефон",
            "имейл",
            "мейл",
            "обади",
            "свържа",
        )
    ):
        return "contact"

    return None


def build_bank_knowledge_payload(
    *,
    question: str,
    language: Optional[str],
) -> Optional[dict[str, Any]]:
    topic = infer_bank_knowledge_topic(question)
    if not topic:
        return None

    is_bg = _is_bg_language(language)
    contact_entries = [
        {
            "label": "Телефон" if is_bg else "Phone",
            "value": "0700 13 014",
        },
        {
            "label": "Имейл" if is_bg else "Email",
            "value": "office@bank.allianz.bg",
        },
        {
            "label": "Адрес" if is_bg else "Address",
            "value": 'София 1407, ул. "Сребърна" 16'
            if is_bg
            else '16 "Srebarna" str., Sofia 1407',
        },
        {
            "label": "Официална страница" if is_bg else "Official page",
            "value": _CONTACT_URL,
            "href": _CONTACT_URL,
        },
    ]
    branch_entries = [
        {
            "label": "Офиси и локации" if is_bg else "Offices and locations",
            "value": _OFFICES_URL,
            "href": _OFFICES_URL,
        },
        {
            "label": "Имейли на офисите" if is_bg else "Office emails",
            "value": _BRANCH_EMAILS_URL,
            "href": _BRANCH_EMAILS_URL,
        },
        contact_entries[2],
    ]
    hours_entries = [
        {
            "label": "Кол център" if is_bg else "Call center",
            "value": "24/7 за банкова информация и блокиране на карти"
            if is_bg
            else "24/7 for bank information and card blocking",
        },
        {
            "label": "Офиси" if is_bg else "Offices",
            "value": "Повечето офиси от официалната страница са с работно време понеделник-петък, 09:00-17:00. Провери точния офис преди посещение."
            if is_bg
            else "Most offices on the official page are listed as Monday-Friday, 09:00-17:00. Check the exact office before visiting.",
        },
        {
            "label": "Страница с офиси" if is_bg else "Office page",
            "value": _OFFICES_URL,
            "href": _OFFICES_URL,
        },
    ]

    if topic == "contact":
        title = "Контакти на банката" if is_bg else "Bank contacts"
        message = (
            'Мога да ти дам официалните контакти на банката: телефон 0700 13 014, имейл office@bank.allianz.bg и адрес ул. "Сребърна" 16, София.'
            if is_bg
            else 'I can give you the bank\'s official contacts: phone 0700 13 014, email office@bank.allianz.bg, and address 16 "Srebarna" str., Sofia.'
        )
        entries = contact_entries
    elif topic == "branches":
        title = "Офиси и локации" if is_bg else "Offices and locations"
        message = (
            "За офиси и локации използвай официалната страница с клоновата мрежа на Allianz Bank. Има и отделен PDF списък със служебните имейли на офисите."
            if is_bg
            else "For offices and locations, use Allianz Bank's official branch network page. There is also a separate PDF list with office email addresses."
        )
        entries = branch_entries
    else:
        title = "Работно време" if is_bg else "Working hours"
        message = (
            "Кол центърът е 24/7 за банкова информация и блокиране на карти. Повечето офиси на официалната страница са с работно време понеделник-петък, 09:00-17:00, но провери точния офис преди посещение."
            if is_bg
            else "The call center is available 24/7 for bank information and card blocking. Most offices on the official page are listed as Monday-Friday, 09:00-17:00, but check the exact office before visiting."
        )
        entries = hours_entries

    return {
        "action": "bank_knowledge",
        "topic": topic,
        "title": title,
        "message": message,
        "entries": entries,
        "sources": [_CONTACT_URL, _OFFICES_URL, _BRANCH_EMAILS_URL],
    }
