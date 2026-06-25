import re
import unicodedata


KNOWN_STORES = [
    "Coop",
    "Conad",
    "Dec\u00f2",
    "Famila",
    "MD",
    "Eurospin",
    "Lidl",
    "Spaccio Alimentare",
    "Crai",
]

CATEGORY_KEYWORDS = {
    "Produce": [
        "banana",
        "banane",
        "arance",
        "limoni",
        "mele",
        "pomodori",
        "insalata",
        "patate",
    ],
    "Dairy": [
        "latte",
        "mozzarella",
        "yogurt",
        "burro",
        "parmigiano",
        "formaggio",
    ],
    "Meat & Fish": [
        "pollo",
        "manzo",
        "salmone",
        "tonno",
        "prosciutto",
        "hamburger",
        "pesce",
    ],
    "Pantry": [
        "pasta",
        "riso",
        "olio",
        "farina",
        "passata",
        "biscotti",
        "caffe",
        "tonno",
    ],
    "Frozen": ["gelato", "surgel", "pizza", "bastoncini"],
    "Drinks": ["acqua", "cola", "birra", "succo", "aranciata", "vino"],
    "Household": [
        "detersivo",
        "carta",
        "sapone",
        "ammorbidente",
        "pannolini",
        "candeggina",
    ],
}


def normalize_store_name(value: str) -> str:
    candidate = value.strip()
    normalized_candidate = _normalize_for_compare(candidate)
    for store in KNOWN_STORES:
        if _normalize_for_compare(store) == normalized_candidate:
            return store
    return candidate


def infer_category(product_name: str, brand: str | None = None) -> str:
    haystack = re.sub(r"\s+", " ", f"{product_name} {brand or ''}".strip().casefold())
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return "Groceries"


def _normalize_for_compare(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char)).strip()
