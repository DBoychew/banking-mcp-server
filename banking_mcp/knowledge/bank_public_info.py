from __future__ import annotations

import asyncio
import html
import re
import time
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

from banking_mcp.knowledge.bank_knowledge import build_bank_knowledge_payload

_CONTACT_URL = "https://www.allianz.bg/bg_BG/individuals/get-in-touch.html"
_OFFICES_URL = "https://www.allianz.bg/bg_BG/individuals/banking/bank-offices-abb.html"
_MANAGEMENT_URL = "https://www.allianz.bg/bg_BG/individuals/about-us/management.html"

_TOPIC_ALIASES = {
    "branch": "branches",
    "branches": "branches",
    "office": "branches",
    "offices": "branches",
    "location": "branches",
    "locations": "branches",
    "contact": "contact",
    "contacts": "contact",
    "hours": "hours",
    "working_hours": "hours",
    "management": "management",
    "people": "management",
    "leaders": "management",
}

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v\xa0]+")
_CFEMAIL_RE = re.compile(
    r'<span class="__cf_email__" data-cfemail="(?P<code>[0-9a-fA-F]+)">.*?</span>',
    re.DOTALL,
)
_EMAIL_RE = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"(?:\+359[\d\s()/.-]{6,}|\d[\d\s()/.-]{6,}\d)")
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_OFFICE_ITEM_RE = re.compile(
    r'<div class="c-accordion__item-wrapper">.*?'
    r"<h3[^>]*>(?P<city>.*?)</h3>.*?"
    r"<p><b>(?P<office_name>.*?)</b><br\s*/?>(?P<body>.*?)</p>",
    re.DOTALL,
)
_MANAGEMENT_SECTION_RE = re.compile(
    r"<h2[^>]*>\s*"
    r"Алианц Банк България АД"
    r"\s*</h2>(?P<section>.*?)<div id=\"ContentVerticalNegative5",
    re.DOTALL,
)

_CACHE_TTL_S = 15 * 60.0
_HTML_CACHE: dict[str, tuple[float, str]] = {}
_HTML_CACHE_LOCK = asyncio.Lock()
_BG_TO_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sht",
    "ъ": "a",
    "ь": "y",
    "ю": "yu",
    "я": "ya",
}


def _is_bg_language(language: Optional[str]) -> bool:
    """Return True if the language code indicates Bulgarian."""
    token = str(language or "").strip().lower()
    return token.startswith("bg")


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _romanize_bg(text: str) -> str:
    return "".join(_BG_TO_LATIN.get(char, char) for char in _normalize(text))


def _romanize_display(text: str) -> str:
    output: list[str] = []
    for char in str(text or ""):
        lower = char.lower()
        latin = _BG_TO_LATIN.get(lower)
        if latin is None:
            output.append(char)
            continue
        output.append(latin.capitalize() if char.isupper() else latin)
    value = "".join(output)
    return value.replace("iya", "ia").replace("Iya", "Ia").replace("Sht", "St")


def _search_key(text: str) -> str:
    normalized = _romanize_bg(text)
    for source, target in (
        ("sht", "st"),
        ("iya", "ia"),
        ("ya", "ia"),
        ("yu", "iu"),
        ("yi", "i"),
        ("yy", "y"),
    ):
        normalized = normalized.replace(source, target)
    return normalized


def _text_matches_query(query: str, candidate: str) -> bool:
    normalized_query = _normalize(query)
    normalized_candidate = _normalize(candidate)
    romanized_query = _search_key(query)
    romanized_candidate = _search_key(candidate)
    return any(
        left and right and (left in right or right in left)
        for left in {normalized_query, romanized_query}
        for right in {normalized_candidate, romanized_candidate}
    )


def _display_text(value: str | None, *, is_bg: bool) -> str:
    text = str(value or "").strip()
    if is_bg or not _CYRILLIC_RE.search(text):
        return text
    return _romanize_display(text)


def normalize_bank_public_info_topic(topic: str | None) -> str | None:
    if topic is None:
        return None
    normalized = _normalize(topic).replace(" ", "_")
    return _TOPIC_ALIASES.get(
        normalized, normalized if normalized in _TOPIC_ALIASES.values() else None
    )


def infer_bank_public_info_topic(question: str) -> str | None:
    normalized = _normalize(question)
    if not normalized:
        return None

    branch_tokens = (
        "branch",
        "branches",
        "office",
        "offices",
        "location",
        "locations",
        "closest office",
        "address",
        "google maps",
        "maps",
        "клон",
        "клонове",
        "офис",
        "офиси",
        "локация",
        "локации",
        "адрес",
        "най-близък",
        "мапс",
        "гугъл мапс",
    )
    hours_tokens = (
        "working hours",
        "opening hours",
        "open today",
        "hours",
        "what time",
        "close",
        "closes",
        "closing",
        "open",
        "opens",
        "работно време",
        "работното време",
        "часове",
        "отворено",
        "затваря",
        "затварят",
        "отваря",
        "отварят",
        "в колко часа",
        "до колко",
        "работи до",
    )
    explicit_management_tokens = (
        "management",
        "board",
        "executive",
        "executives",
        "director",
        "directors",
        "ceo",
        "chairman",
        "procurator",
        "управление",
        "ръководство",
        "изпълнителен",
        "изпълнителни",
        "директор",
        "директори",
        "прокурист",
    )
    human_contact_tokens = (
        "talk to a human",
        "talk to a person",
        "human agent",
        "customer service",
        "support agent",
        "representative",
        "operator",
        "contact person",
        "свържи ме",
        "свържи с",
        "свържете ме",
        "искам човек",
        "искам служител",
        "оператор",
        "представител",
        "човек",
    )
    contact_tokens = (
        "contact",
        "contacts",
        "phone",
        "email",
        "mail",
        "call center",
        "support",
        "swift",
        "контакт",
        "контакти",
        "телефон",
        "имейл",
        "мейл",
        "обади",
        "свържа",
        "връзка",
        "суифт",
        "служител",
        "служители",
    )

    if any(token in normalized for token in human_contact_tokens):
        return "contact"

    if any(token in normalized for token in hours_tokens):
        if (
            any(token in normalized for token in branch_tokens)
            or "office" in normalized
            or "офис" in normalized
        ):
            return "hours"

    if any(token in normalized for token in explicit_management_tokens):
        return "management"

    if any(token in normalized for token in branch_tokens):
        return "branches"

    if any(token in normalized for token in contact_tokens):
        return "contact"

    return None


def _is_map_request(question: str) -> bool:
    normalized = _normalize(question)
    if not normalized:
        return False
    return any(
        token in normalized
        for token in (
            "google maps",
            "maps",
            "гугъл мапс",
            "мапс",
        )
    )


def _google_maps_url(
    *, office_name: str | None, city: str | None, address: str | None
) -> str | None:
    query = " ".join(
        part.strip()
        for part in (office_name or "", address or "", city or "")
        if str(part).strip()
    )
    if not query:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def _closing_time(working_hours: str | None) -> str | None:
    text = str(working_hours or "").strip()
    if not text:
        return None
    matches = re.findall(r"\b(\d{1,2}:\d{2})\b", text)
    if not matches:
        return None
    return matches[-1]


def _decode_cfemail(encoded: str) -> str:
    if len(encoded) < 2:
        return ""
    key = int(encoded[:2], 16)
    decoded: list[str] = []
    for index in range(2, len(encoded), 2):
        decoded.append(chr(int(encoded[index : index + 2], 16) ^ key))
    return "".join(decoded)


def _decode_cfemails_in_html(raw_html: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return _decode_cfemail(match.group("code"))

    return _CFEMAIL_RE.sub(_replace, raw_html)


def _html_to_text(fragment: str) -> str:
    decoded = _decode_cfemails_in_html(fragment)
    decoded = _BR_RE.sub("\n", decoded)
    decoded = _TAG_RE.sub("", decoded)
    decoded = html.unescape(decoded)
    lines = [_WS_RE.sub(" ", line).strip() for line in decoded.splitlines()]
    return "\n".join(line for line in lines if line)


def _clean_inline_text(fragment: str) -> str:
    return " ".join(_html_to_text(fragment).split())


def _split_phones(raw_value: str) -> list[str]:
    normalized = (
        str(raw_value or "").replace(" и ", ";").replace(", ", ";").replace(" / ", "/")
    )
    items = [item.strip(" ;") for item in normalized.split(";") if item.strip(" ;")]
    return items


def _lines_to_label_map(text: str) -> dict[str, str]:
    labels = {
        "адрес": "address",
        "телефон": "phone",
        "e-mail": "email",
        "email": "email",
        "работно време": "working_hours",
        "e-mail:": "email",
    }
    result: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        key_match = None
        value_match = None
        for label_text, target_key in labels.items():
            prefix = f"{label_text}:"
            if _normalize(line).startswith(prefix):
                key_match = target_key
                value_match = line.split(":", 1)[1].strip()
                break
        if key_match:
            result[key_match] = value_match or result.get(key_match, "")
            current_key = key_match
            continue
        if current_key:
            joined = " ".join(
                part for part in (result.get(current_key, ""), line) if part
            )
            result[current_key] = joined.strip()
    return result


def _first_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text)
    if not match:
        return None
    return match.group(0)


def _normalize_phone_display(raw_phone: str) -> str:
    return " ".join(str(raw_phone or "").split())


async def _get_cached_html(*, url: str, client: httpx.AsyncClient | None = None) -> str:
    now = time.monotonic()
    cached = _HTML_CACHE.get(url)
    if cached and now - cached[0] < _CACHE_TTL_S:
        return cached[1]

    async with _HTML_CACHE_LOCK:
        cached = _HTML_CACHE.get(url)
        if cached and now - cached[0] < _CACHE_TTL_S:
            return cached[1]

        if client is None:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True
            ) as owned_client:
                response = await owned_client.get(url)
        else:
            response = await client.get(url)
        response.raise_for_status()
        html_text = str(response.text or "")
        _HTML_CACHE[url] = (time.monotonic(), html_text)
        return html_text


def _parse_offices(raw_html: str) -> list[dict[str, Any]]:
    offices: list[dict[str, Any]] = []
    decoded_html = _decode_cfemails_in_html(raw_html)
    for match in _OFFICE_ITEM_RE.finditer(decoded_html):
        city = _clean_inline_text(match.group("city"))
        office_name = _clean_inline_text(match.group("office_name"))
        fields = _lines_to_label_map(_html_to_text(match.group("body")))
        email = _first_email(match.group("body")) or fields.get("email")
        office = {
            "city": city,
            "office_name": office_name,
            "address": fields.get("address"),
            "phones": _split_phones(fields.get("phone", "")),
            "email": str(email or "").strip() or None,
            "working_hours": fields.get("working_hours"),
            "source_url": _OFFICES_URL,
        }
        if office_name and (
            office.get("address") or office.get("email") or office.get("phones")
        ):
            offices.append(office)
    return offices


def _extract_contact_info(contact_html: str, management_html: str) -> dict[str, Any]:
    decoded_contact = _decode_cfemails_in_html(contact_html)
    decoded_management = _decode_cfemails_in_html(management_html)

    contact_match = re.search(
        r"<p><b>\s*Алианц Банк България"
        r"\s*</b><br\s*/?>\s*</p>\s*<p>(?P<address>.*?)</p>(?P<tail>.*?)(?:</div>|</section>)",
        decoded_contact,
        re.DOTALL,
    )
    address = None
    email = None
    if contact_match:
        address = " ".join(_html_to_text(contact_match.group("address")).split())
        email = _first_email(contact_match.group("tail"))

    management_section_match = _MANAGEMENT_SECTION_RE.search(decoded_management)
    management_section = (
        management_section_match.group("section")
        if management_section_match
        else decoded_management
    )
    management_section_text = _html_to_text(management_section)
    if not email:
        email = _first_email(management_section)

    phone = None
    phone_line_match = re.search(
        r"Телефон:\s*(?P<phone>.+)",
        management_section_text,
    )
    if phone_line_match:
        phone = _normalize_phone_display(phone_line_match.group("phone"))
    else:
        raw_phone_match = re.search(r"0700\s*13\s*014", decoded_contact)
        if raw_phone_match:
            phone = "0700 13 014"

    fax_numbers: list[str] = []
    fax_block_match = re.search(
        r"Факс:\s*(?P<fax>.*?)(?:\n\S|$)",
        management_section_text,
        re.DOTALL,
    )
    if fax_block_match:
        fax_lines = [
            line.strip()
            for line in fax_block_match.group("fax").splitlines()
            if line.strip()
        ]
        fax_numbers = fax_lines[:2]

    swift_match = re.search(r"SWIFT:\s*(?P<swift>[A-Z0-9]+)", management_section_text)
    swift = swift_match.group("swift") if swift_match else None

    return {
        "phone": phone,
        "email": email,
        "address": address,
        "fax_numbers": fax_numbers,
        "swift": swift,
    }


def _extract_people_block(
    section_html: str, title_pattern: str, group: str
) -> list[dict[str, Any]]:
    match = re.search(title_pattern, section_html, re.DOTALL)
    if not match:
        return []
    lines = [
        line.strip()
        for line in _html_to_text(match.group("body")).splitlines()
        if line.strip()
    ]
    people: list[dict[str, Any]] = []
    for line in lines:
        normalized_line = " ".join(line.split())
        if not normalized_line:
            continue
        if " - " in normalized_line:
            name, role = normalized_line.split(" - ", 1)
        elif " – " in normalized_line:
            name, role = normalized_line.split(" – ", 1)
        else:
            name, role = normalized_line, ""
        people.append(
            {
                "name": name.strip(),
                "role": role.strip() or None,
                "group": group,
            }
        )
    return people


def _extract_management_data(raw_html: str) -> dict[str, Any]:
    decoded_html = _decode_cfemails_in_html(raw_html)
    section_match = _MANAGEMENT_SECTION_RE.search(decoded_html)
    section_html = section_match.group("section") if section_match else decoded_html

    supervisory_board = _extract_people_block(
        section_html,
        r"<p><b>Надзорен съвет:</b></p>\s*<p>(?P<body>.*?)</p>",
        "supervisory_board",
    )
    management_board = _extract_people_block(
        section_html,
        r"<p><b>Управителен съвет:</b></p>\s*<p>(?P<body>.*?)</p>",
        "management_board",
    )
    representatives = _extract_people_block(
        section_html,
        r"<p><b>Лица,\s*представляващи дружеството</b>\s*:?\s*</p>\s*"
        r"<p>(?P<body>.*?)</p>",
        "representatives",
    )
    return {
        "supervisory_board": supervisory_board,
        "management_board": management_board,
        "representatives": representatives,
    }


def _infer_city(question: str, offices: list[dict[str, Any]]) -> str | None:
    normalized_question = _normalize(question)
    if not normalized_question:
        return None
    seen: set[str] = set()
    for office in offices:
        display_city = str(office.get("city") or "").strip()
        if not display_city or display_city in seen:
            continue
        seen.add(display_city)
        if _text_matches_query(question, display_city):
            return display_city
    return None


def _filter_offices(
    *,
    offices: list[dict[str, Any]],
    city: str | None,
    office_query: str | None,
    question: str,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    resolved_city = str(city or "").strip() or _infer_city(question, offices)
    normalized_city = _normalize(resolved_city)
    normalized_query = _normalize(office_query or "")
    has_filter = bool(normalized_city or normalized_query)

    filtered = list(offices)
    if normalized_city:
        filtered = [
            office
            for office in filtered
            if _text_matches_query(normalized_city, str(office.get("city") or ""))
            or _text_matches_query(
                normalized_city, str(office.get("office_name") or "")
            )
            or _text_matches_query(normalized_city, str(office.get("address") or ""))
        ]
    if normalized_query:
        filtered = [
            office
            for office in filtered
            if _text_matches_query(
                normalized_query, str(office.get("office_name") or "")
            )
            or _text_matches_query(normalized_query, str(office.get("address") or ""))
            or _text_matches_query(normalized_query, str(office.get("city") or ""))
        ]
    return filtered, resolved_city or None, has_filter


def _find_person_query(question: str, people: list[dict[str, Any]]) -> str | None:
    normalized_question = _normalize(question)
    if not normalized_question:
        return None
    for person in people:
        name = str(person.get("name") or "").strip()
        if name and _text_matches_query(question, name):
            return name
    return None


def _entry(
    label: str, value: str | None, href: str | None = None
) -> dict[str, str | None]:
    return {"label": label, "value": value, "href": href}


def _contact_payload(
    *,
    contact_info: dict[str, Any],
    language: str | None,
) -> dict[str, Any]:
    is_bg = _is_bg_language(language)
    phone = str(contact_info.get("phone") or "0700 13 014").strip()
    email = str(contact_info.get("email") or "").strip() or None
    address = str(contact_info.get("address") or "").strip() or None
    swift = str(contact_info.get("swift") or "").strip() or None
    fax_numbers = [
        str(item).strip()
        for item in (contact_info.get("fax_numbers") or [])
        if str(item).strip()
    ]

    entries = [
        _entry(
            "Телефон" if is_bg else "Phone",
            phone,
            f"tel:{phone.replace(' ', '')}" if phone else None,
        ),
    ]
    if email:
        entries.append(
            _entry(
                "Имейл" if is_bg else "Email",
                email,
                f"mailto:{email}",
            )
        )
    if address:
        entries.append(
            _entry(
                "Адрес" if is_bg else "Address", address, None
            )
        )
    if swift:
        entries.append(_entry("SWIFT", swift, None))
    if fax_numbers:
        entries.append(
            _entry(
                "Факс" if is_bg else "Fax",
                "; ".join(fax_numbers),
                None,
            )
        )
    entries.append(
        _entry(
            "Официална страница" if is_bg else "Official page",
            _CONTACT_URL,
            _CONTACT_URL,
        )
    )

    message = (
        f"Официалните контакти на банката са: "
        f"телефон {phone}"
        + (f", имейл {email}" if email else "")
        + (f", адрес {address}" if address else "")
        + (f", SWIFT {swift}" if swift else "")
        + "."
        if is_bg
        else f"The bank's public contact channels are: phone {phone}"
        + (f", email {email}" if email else "")
        + (f", address {address}" if address else "")
        + (f", SWIFT {swift}" if swift else "")
        + "."
    )
    return {
        "action": "bank_knowledge",
        "topic": "contact",
        "title": "Контакти на банката" if is_bg else "Bank contacts",
        "message": message,
        "entries": entries,
        "sources": [_CONTACT_URL, _MANAGEMENT_URL],
    }


def _branches_payload(
    *,
    offices: list[dict[str, Any]],
    resolved_city: str | None,
    language: str | None,
    topic: str,
    limit: int,
    question: str,
) -> dict[str, Any]:
    is_bg = _is_bg_language(language)
    limited = offices[:limit]
    maps_requested = _is_map_request(question)
    if topic == "hours":
        title = "Работно време" if is_bg else "Working hours"
        entries = [
            _entry(
                f"{_display_text(str(office.get('office_name') or ''), is_bg=is_bg)} "
                f"({_display_text(str(office.get('city') or ''), is_bg=is_bg)})",
                _display_text(
                    str(office.get("working_hours") or "").strip(), is_bg=is_bg
                )
                or (
                    "Няма публикувани часове" if is_bg else "No public hours listed"
                ),
                _google_maps_url(
                    office_name=str(office.get("office_name") or "").strip(),
                    city=str(office.get("city") or "").strip(),
                    address=str(office.get("address") or "").strip(),
                ),
            )
            for office in limited
        ]
        if not limited:
            message = (
                "Не намерих публично обявено работно време за това търсене."
                if is_bg
                else "I could not find public working hours for that search."
            )
        elif len(offices) == 1:
            office = offices[0]
            office_name = _display_text(
                str(office.get("office_name") or "").strip(), is_bg=is_bg
            )
            city_name = _display_text(
                str(office.get("city") or "").strip(), is_bg=is_bg
            )
            hours_value = _display_text(
                str(office.get("working_hours") or "").strip(), is_bg=is_bg
            )
            closing_time = _closing_time(str(office.get("working_hours") or "").strip())
            if closing_time:
                message = (
                    f"{office_name} в {city_name} работи {hours_value} и затваря в {closing_time}."
                    if is_bg
                    else f"{office_name} in {city_name} works {hours_value} and closes at {closing_time}."
                )
            else:
                message = (
                    f"{office_name} в {city_name} работи {hours_value}."
                    if is_bg
                    else f"{office_name} in {city_name} works {hours_value}."
                )
        else:
            common_hours = str(limited[0].get("working_hours") or "").strip()
            if resolved_city:
                message = (
                    f"Намерих {len(offices)} офиса/и за {resolved_city}. "
                    f"Показвам публично обявеното работно време."
                    if is_bg
                    else f"I found {len(offices)} office(s) for {resolved_city}. Showing the public working hours."
                )
            else:
                message = (
                    f"Най-често публикуваното работно време е {common_hours}. "
                    f"Показвам {len(limited)} примера."
                    if is_bg
                    else f"The most common published office hours are {common_hours}. Showing {len(limited)} examples."
                )
    else:
        title = "Офиси и локации" if is_bg else "Office locations"
        entries = [
            _entry(
                f"{_display_text(str(office.get('office_name') or ''), is_bg=is_bg)} "
                f"({_display_text(str(office.get('city') or ''), is_bg=is_bg)})",
                "; ".join(
                    part
                    for part in (
                        _display_text(
                            str(office.get("address") or "").strip(), is_bg=is_bg
                        ),
                        ", ".join(office.get("phones") or []),
                        str(office.get("email") or "").strip(),
                        _display_text(
                            str(office.get("working_hours") or "").strip(), is_bg=is_bg
                        ),
                    )
                    if part
                ),
                _google_maps_url(
                    office_name=str(office.get("office_name") or "").strip(),
                    city=str(office.get("city") or "").strip(),
                    address=str(office.get("address") or "").strip(),
                ),
            )
            for office in limited
        ]
        if not limited:
            message = (
                "Не намерих публично обявен офис за това търсене."
                if is_bg
                else "I could not find a public office matching that search."
            )
        elif len(offices) == 1:
            office = offices[0]
            phones = ", ".join(office.get("phones") or [])
            maps_url = _google_maps_url(
                office_name=str(office.get("office_name") or "").strip(),
                city=str(office.get("city") or "").strip(),
                address=str(office.get("address") or "").strip(),
            )
            message = (
                f"Намерих {office.get('office_name')} в {office.get('city')}: "
                f"{office.get('address')}. "
                f"Телефон: {phones}. "
                f"Имейл: {office.get('email')}. "
                f"Работно време: {office.get('working_hours')}."
                + (f" Google Maps: {maps_url}." if maps_requested and maps_url else "")
                if is_bg
                else f"I found {_display_text(str(office.get('office_name') or ''), is_bg=is_bg)} "
                f"in {_display_text(str(office.get('city') or ''), is_bg=is_bg)}: "
                f"{_display_text(str(office.get('address') or ''), is_bg=is_bg)}. "
                f"Phone: {phones}. Email: {office.get('email')}. "
                f"Working hours: {_display_text(str(office.get('working_hours') or ''), is_bg=is_bg)}."
                + (f" Google Maps: {maps_url}." if maps_requested and maps_url else "")
            )
        else:
            scope = resolved_city or (
                "тази заявка" if is_bg else "this request"
            )
            message = (
                f"Намерих {len(offices)} офиса/и за {scope}. "
                f"Показвам първите {len(limited)}."
                if is_bg
                else f"I found {len(offices)} office(s) for {scope}. Showing the first {len(limited)}."
            )

    return {
        "action": "bank_knowledge",
        "topic": topic,
        "title": title,
        "message": message,
        "entries": entries,
        "resolved_city": resolved_city,
        "displayed_count": len(limited),
        "total_count": len(offices),
        "maps_requested": maps_requested,
        "sources": [_OFFICES_URL],
    }


def _management_payload(
    *,
    management_data: dict[str, Any],
    person_query: str | None,
    language: str | None,
    limit: int,
) -> dict[str, Any]:
    is_bg = _is_bg_language(language)
    representatives = list(management_data.get("representatives") or [])
    people = (
        representatives
        or list(management_data.get("management_board") or [])
        or list(management_data.get("supervisory_board") or [])
    )
    if person_query:
        normalized_person_query = _normalize(person_query)
        people = [
            person
            for person in people
            if _text_matches_query(
                normalized_person_query, str(person.get("name") or "")
            )
        ]
    limited = people[:limit]
    entries = [
        _entry(
            _display_text(str(person.get("name") or "").strip(), is_bg=is_bg),
            _display_text(
                str(person.get("role") or "").strip()
                or str(person.get("group") or "").strip(),
                is_bg=is_bg,
            ),
        )
        for person in limited
        if str(person.get("name") or "").strip()
    ]
    if person_query and limited:
        message = (
            f"Намерих публично обявена информация за {limited[0].get('name')}."
            if is_bg
            else f"I found public information for {_display_text(str(limited[0].get('name') or ''), is_bg=is_bg)}."
        )
    elif limited:
        message = (
            "Публично обявените представители на банката са:"
            if is_bg
            else "The bank's publicly listed representatives are:"
        )
    else:
        message = (
            "Не намерих публично обявена информация за това име."
            if is_bg
            else "I could not find publicly listed information for that name."
        )

    return {
        "action": "bank_knowledge",
        "topic": "management",
        "title": "Ръководство" if is_bg else "Management",
        "message": message,
        "entries": entries,
        "sources": [_MANAGEMENT_URL],
    }


async def fetch_bank_public_info_payload(
    *,
    question: str = "",
    topic: str | None = None,
    city: str | None = None,
    office_query: str | None = None,
    person_query: str | None = None,
    language: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    resolved_topic = normalize_bank_public_info_topic(
        topic
    ) or infer_bank_public_info_topic(question)
    if not resolved_topic:
        return {}

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            if resolved_topic in {"branches", "hours"}:
                offices_html = await _get_cached_html(url=_OFFICES_URL, client=client)
                offices = _parse_offices(offices_html)
                filtered_offices, resolved_city, has_filter = _filter_offices(
                    offices=offices,
                    city=city,
                    office_query=office_query,
                    question=question,
                )
                return _branches_payload(
                    offices=filtered_offices if has_filter else offices,
                    resolved_city=resolved_city,
                    language=language,
                    topic=resolved_topic,
                    limit=limit,
                    question=question,
                )

            if resolved_topic == "management":
                management_html = await _get_cached_html(
                    url=_MANAGEMENT_URL, client=client
                )
                management_data = _extract_management_data(management_html)
                resolved_person_query = str(
                    person_query or ""
                ).strip() or _find_person_query(
                    question,
                    list(management_data.get("representatives") or [])
                    + list(management_data.get("management_board") or [])
                    + list(management_data.get("supervisory_board") or []),
                )
                return _management_payload(
                    management_data=management_data,
                    person_query=resolved_person_query,
                    language=language,
                    limit=limit,
                )

            contact_html, management_html = await asyncio.gather(
                _get_cached_html(url=_CONTACT_URL, client=client),
                _get_cached_html(url=_MANAGEMENT_URL, client=client),
            )
            return _contact_payload(
                contact_info=_extract_contact_info(contact_html, management_html),
                language=language,
            )
    except Exception:
        fallback = build_bank_knowledge_payload(question=question, language=language)
        if fallback:
            return fallback
        is_bg = _is_bg_language(language)
        return {
            "action": "bank_knowledge",
            "topic": resolved_topic,
            "title": (
                "Публична информация" if is_bg else "Public bank information"
            ),
            "message": (
                "Не успях да заредя актуалните данни от официалния сайт. "
                "Провери директно източниците по-долу."
                if is_bg
                else "I could not load the latest information from the official website. Check the official sources below directly."
            ),
            "entries": [
                _entry(
                    "Клонова мрежа" if is_bg else "Branch network",
                    _OFFICES_URL,
                    _OFFICES_URL,
                ),
                _entry(
                    "Контакти" if is_bg else "Contacts",
                    _CONTACT_URL,
                    _CONTACT_URL,
                ),
                _entry(
                    "Управление" if is_bg else "Management",
                    _MANAGEMENT_URL,
                    _MANAGEMENT_URL,
                ),
            ],
            "sources": [_CONTACT_URL, _OFFICES_URL, _MANAGEMENT_URL],
        }
