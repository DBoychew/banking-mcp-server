from typing import Any, Iterable


SEMANTIC_CATEGORY_KEY_ALIASES = {
    "subscriptions": "subscription",
    "bank_fees": "fees",
    "loan_repayment": "loan",
    "cash_atm": "cash",
}


SEMANTIC_CATEGORY_CATALOG: dict[str, dict[str, Any]] = {
    "food": {
        "aliases": {
            "храни",
            "храна",
            "хранителен",
            "супермаркет",
            "бакалия",
            "food",
            "grocery",
            "groceries",
            "supermarket",
        },
        "keywords": {
            "kaufland",
            "lidl",
            "billa",
            "fantastico",
            "super market boni",
            "t market",
            "supermarket",
            "grocery",
            "кауфланд",
            "лидл",
            "била",
            "фантастико",
            "храни",
            "супермаркет",
        },
        "directions": {"debit"},
        "label_en": "food",
        "label_bg": "храна",
        "reason_en": "I match supermarket and everyday food merchants such as Kaufland, Lidl, Billa, Fantastico, and similar grocery descriptions.",
        "reason_bg": "Съпоставям с хранителни вериги и ежедневни хранителни разходи като Kaufland, Lidl, Billa, Fantastico и подобни описания.",
    },
    "dining": {
        "aliases": {
            "ресторан",
            "заведен",
            "доставк",
            "кафе",
            "restaurant",
            "restaurants",
            "delivery",
            "takeaway",
            "takeout",
            "coffee",
        },
        "keywords": {
            "restaurant",
            "bar",
            "cafe",
            "coffee",
            "foodpanda",
            "glovo",
            "takeaway",
            "takeout",
            "delivery",
            "ресторан",
            "заведен",
            "доставк",
            "кафе",
        },
        "directions": {"debit"},
        "label_en": "restaurants and delivery",
        "label_bg": "заведения и доставки",
        "reason_en": "I look for restaurants, cafes, delivery platforms, and takeaway-style merchants.",
        "reason_bg": "Търся ресторанти, кафенета, delivery платформи и takeaway търговци.",
    },
    "fuel": {
        "aliases": {
            "горив",
            "бензин",
            "дизел",
            "бензиностанц",
            "fuel",
            "petrol",
            "gas station",
        },
        "keywords": {
            "petrol",
            "eko",
            "omv",
            "shell",
            "lukoil",
            "rompetrol",
            "insaoil",
            "sevi oyl",
            "gas stations eko",
            "горив",
            "бензин",
            "бензиностанц",
        },
        "directions": {"debit"},
        "label_en": "fuel",
        "label_bg": "гориво",
        "reason_en": "I match fuel-station merchants and descriptors such as OMV, EKO, Shell, and petrol-related wording.",
        "reason_bg": "Съпоставям с бензиностанции и описания като OMV, EKO, Shell и текст за гориво.",
    },
    "car": {
        "aliases": {
            "кола",
            "колата",
            "авто",
            "автомобил",
            "car",
            "vehicle",
            "auto",
        },
        "keywords": {
            "fuel",
            "petrol",
            "gas",
            "station",
            "eko",
            "omv",
            "shell",
            "parking",
            "park",
            "vinette",
            "vignette",
            "toll",
            "service",
            "serviz",
            "repair",
            "insurance",
            "fine",
            "горив",
            "бензин",
            "паркинг",
            "винетк",
            "сервиз",
            "гуми",
            "застрах",
            "глоба",
        },
        "directions": {"debit"},
        "label_en": "car expenses",
        "label_bg": "разходи за кола",
        "reason_en": "This is a broader category that may include fuel, parking, service, insurance, tolls, and similar vehicle costs.",
        "reason_bg": "Това е по-широка категория, в която могат да влизат гориво, паркинг, сервиз, застраховки, такси и други разходи за автомобил.",
    },
    "transport": {
        "aliases": {
            "транспорт",
            "такси",
            "метро",
            "автобус",
            "влак",
            "transport",
            "taxi",
            "uber",
            "bolt",
            "bus",
            "metro",
            "train",
        },
        "keywords": {
            "bolt",
            "uber",
            "taxi",
            "metro",
            "bus",
            "train",
            "rail",
            "такси",
            "метро",
            "автобус",
            "влак",
            "транспорт",
        },
        "directions": {"debit"},
        "label_en": "transport",
        "label_bg": "транспорт",
    },
    "home": {
        "aliases": {
            "дом",
            "дома",
            "мебели",
            "ремонт",
            "home",
            "furniture",
            "repair",
            "renovation",
        },
        "keywords": {
            "ikea",
            "praktiker",
            "jysk",
            "toplivo",
            "home max",
            "мебел",
            "ремонт",
            "furniture",
            "repair",
            "renovation",
        },
        "directions": {"debit"},
        "label_en": "home",
        "label_bg": "дом",
    },
    "utilities": {
        "aliases": {
            "битов",
            "битови сметки",
            "ток",
            "вода",
            "интернет",
            "телефон",
            "utility",
            "utilities",
            "electricity",
            "water",
            "internet",
            "phone",
        },
        "keywords": {
            "electricity",
            "water",
            "internet",
            "mobile",
            "phone",
            "telecom",
            "vivacom",
            "a1",
            "yettel",
            "cez",
            "evn",
            "energo",
            "ток",
            "вода",
            "интернет",
            "телефон",
            "битов",
        },
        "directions": {"debit"},
        "label_en": "utilities",
        "label_bg": "битови сметки",
    },
    "health": {
        "aliases": {
            "здрав",
            "аптек",
            "лекар",
            "болниц",
            "стомат",
            "лаборатор",
            "health",
            "pharmacy",
            "doctor",
            "clinic",
            "hospital",
            "dental",
        },
        "keywords": {
            "pharmacy",
            "doctor",
            "clinic",
            "hospital",
            "medical",
            "medlab",
            "dental",
            "аптек",
            "лекар",
            "болниц",
            "стомат",
            "здрав",
            "лаборатор",
        },
        "directions": {"debit"},
        "label_en": "health",
        "label_bg": "здраве",
    },
    "shopping": {
        "aliases": {
            "пазаруван",
            "дреха",
            "обув",
            "shopping",
            "fashion",
            "clothes",
            "shoes",
            "apparel",
        },
        "keywords": {
            "fashion",
            "clothes",
            "shoes",
            "apparel",
            "mall",
            "zara",
            "hm",
            "дреха",
            "обув",
            "мода",
            "пазаруван",
        },
        "directions": {"debit"},
        "label_en": "shopping",
        "label_bg": "пазаруване",
    },
    "family": {
        "aliases": {
            "деца",
            "семей",
            "училищ",
            "играч",
            "курс",
            "family",
            "kids",
            "child",
            "school",
            "toy",
        },
        "keywords": {
            "school",
            "toy",
            "lesson",
            "course",
            "kids",
            "child",
            "училищ",
            "играч",
            "курс",
        },
        "directions": {"debit"},
        "label_en": "family or kids",
        "label_bg": "семейство или деца",
    },
    "subscription": {
        "aliases": {
            "абонамент",
            "абонаменти",
            "subscription",
            "subscriptions",
            "streaming",
            "saas",
        },
        "keywords": {
            "subscription",
            "netflix",
            "spotify",
            "youtube",
            "adobe",
            "microsoft",
            "google one",
            "chatgpt",
            "github",
            "абонамент",
        },
        "directions": {"debit"},
        "label_en": "subscriptions",
        "label_bg": "абонаменти",
    },
    "fees": {
        "aliases": {
            "банкови такси",
            "такса",
            "комисион",
            "bank fee",
            "fees",
            "fee",
            "commission",
        },
        "keywords": {
            "fee",
            "fees",
            "charge",
            "commission",
            "такс",
            "комисион",
        },
        "directions": {"debit"},
        "label_en": "bank fees",
        "label_bg": "банкови такси",
    },
    "loan": {
        "aliases": {
            "погасител",
            "погасяван",
            "вноск",
            "кредит",
            "loan",
            "repayment",
            "principal",
            "interest",
        },
        "keywords": {
            "погас",
            "погасяван",
            "погасител",
            "вноск",
            "главниц",
            "лихв",
            "кредит",
            "loan",
            "repay",
            "principal",
            "interest",
        },
        "directions": {"debit"},
        "label_en": "loan repayments",
        "label_bg": "погасяване на кредит",
    },
    "income": {
        "aliases": {
            "заплат",
            "аванс",
            "хонорар",
            "приход",
            "salary",
            "income",
            "payroll",
            "bonus",
        },
        "keywords": {
            "salary",
            "payroll",
            "bonus",
            "bisera",
            "credit transfer",
            "заплат",
            "аванс",
            "хонорар",
            "приход",
            "получен",
        },
        "directions": {"credit"},
        "label_en": "income",
        "label_bg": "приходи",
    },
    "cash": {
        "aliases": {
            "кеш",
            "в брой",
            "теглене",
            "банкомат",
            "cash",
            "atm",
            "withdraw",
            "withdrawal",
        },
        "keywords": {
            "atm",
            "cash",
            "withdraw",
            "withdrawal",
            "теглене",
            "в брой",
            "банкомат",
        },
        "directions": {"debit"},
        "label_en": "cash or ATM",
        "label_bg": "кеш или ATM",
    },
    "travel": {
        "aliases": {
            "пътув",
            "хотел",
            "нощувк",
            "travel",
            "trip",
            "vacation",
            "hotel",
            "booking",
            "airbnb",
        },
        "keywords": {
            "hotel",
            "booking",
            "airbnb",
            "wizz",
            "ryanair",
            "flight",
            "hostel",
            "travel",
            "хотел",
            "нощувк",
            "пътув",
        },
        "directions": {"debit"},
        "label_en": "travel",
        "label_bg": "пътуване",
    },
    "entertainment": {
        "aliases": {
            "развлеч",
            "кино",
            "игр",
            "концерт",
            "театър",
            "entertainment",
            "movie",
            "gaming",
            "game",
            "cinema",
            "theatre",
        },
        "keywords": {
            "cinema",
            "movie",
            "theatre",
            "steam",
            "playstation",
            "xbox",
            "concert",
            "gaming",
            "развлеч",
            "кино",
            "игр",
            "концерт",
            "театър",
        },
        "directions": {"debit"},
        "label_en": "entertainment",
        "label_bg": "развлечения",
    },
    "transfer": {
        "aliases": {
            "transfer",
            "transfers",
            "payment transfer",
            "prevod",
            "превод",
            "преводи",
            "нареден превод",
            "получен превод",
        },
        "keywords": {
            "transfer",
            "bisera",
            "sepa",
            "swift",
            "credit transfer",
            "received transfer",
            "payment transfer",
            "prevod",
            "превод",
            "преводи",
            "получен",
            "наредн",
            "f73",
        },
        "directions": {"debit", "credit"},
        "label_en": "transfers",
        "label_bg": "преводи",
    },
}


def canonical_semantic_category(category: str | None) -> str:
    token = str(category or "").strip().lower()
    return SEMANTIC_CATEGORY_KEY_ALIASES.get(token, token)


def semantic_category_definition(category: str | None) -> dict[str, Any]:
    return SEMANTIC_CATEGORY_CATALOG.get(canonical_semantic_category(category), {})


def matched_semantic_category_definitions(
    query_normalized: str,
) -> list[dict[str, Any]]:
    if not query_normalized:
        return []
    matched: list[dict[str, Any]] = []
    for definition in SEMANTIC_CATEGORY_CATALOG.values():
        aliases = definition.get("aliases") or set()
        if any(alias in query_normalized for alias in aliases):
            matched.append(definition)
    return matched


def semantic_category_keywords_for_query(query_normalized: str) -> set[str]:
    expanded: set[str] = set()
    for definition in matched_semantic_category_definitions(query_normalized):
        expanded.update(
            str(keyword).strip().lower()
            for keyword in definition.get("keywords") or set()
        )
    return {token for token in expanded if token}


def semantic_category_directions_for_query(query_normalized: str) -> set[str]:
    directions: set[str] = set()
    for definition in matched_semantic_category_definitions(query_normalized):
        directions.update(
            str(direction).strip().lower()
            for direction in (definition.get("directions") or set())
            if str(direction).strip()
        )
    return directions


def semantic_category_label(category: str | None, *, is_bg: bool) -> str:
    definition = semantic_category_definition(category)
    if not definition:
        token = canonical_semantic_category(category) or (
            "category"
            if not is_bg
            else "категория"
        )
        return token
    return str(definition["label_bg" if is_bg else "label_en"])


def semantic_category_reasoning(category: str | None, *, is_bg: bool) -> str | None:
    definition = semantic_category_definition(category)
    if not definition:
        return None
    key = "reason_bg" if is_bg else "reason_en"
    value = str(definition.get(key) or "").strip()
    return value or None


def iter_semantic_query_aliases() -> Iterable[tuple[str, tuple[str, ...]]]:
    for category, definition in SEMANTIC_CATEGORY_CATALOG.items():
        aliases = tuple(
            str(alias) for alias in sorted(definition.get("aliases") or set())
        )
        if aliases:
            yield category, aliases
