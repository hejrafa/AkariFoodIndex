#!/usr/bin/env python3
"""Build market-specific, read-only Akari packaged-food indexes.

The builder streams an unmodified Open Food Facts CSV or JSONL export,
normalizes label data, validates barcodes and nutrition, groups duplicate
product identities, and emits one SQLite database per requested market.

Open Food Facts remains a separate ODbL-derived database. Akari's BLS/USDA
reference overlay is intentionally not copied into this artifact.
"""

from __future__ import annotations

import argparse
import functools
from collections import Counter
import contextlib
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Iterator


from classify_artwork import classify, VERSION as CLASSIFICATION_VERSION
from food_taxonomy import search_names
from normalize_off_nutrition import normalize_record
from serving_validation import accepts as accepts_serving_label

SCHEMA_VERSION = 4
SUPPORTED_NUTRIENTS = {
    "calories": ("energy-kcal_100g",),
    "carbs": ("carbohydrates_100g",),
    "protein": ("proteins_100g", "protein_100g"),
    "fat": ("fat_100g",),
    "fiber": ("fiber_100g",),
    "sugar": ("sugars_100g",),
    "saturatedFat": ("saturated-fat_100g",),
    "polyunsaturatedFat": ("polyunsaturated-fat_100g",),
    "sodium": ("sodium_100g",),
    "magnesium": ("magnesium_100g",),
    "potassium": ("potassium_100g",),
    "calcium": ("calcium_100g",),
    "iron": ("iron_100g",),
    "iodine": ("iodine_100g",),
    "zinc": ("zinc_100g",),
    "selenium": ("selenium_100g",),
    "vitaminA": ("vitamin-a_100g",),
    "vitaminD": ("vitamin-d_100g",),
    "vitaminB12": ("vitamin-b12_100g",),
    "folate": ("folates_100g", "vitamin-b9_100g"),
    "vitaminC": ("vitamin-c_100g",),
    "caffeine": ("caffeine_100g",),
}
MICRONUTRIENTS = {
    "magnesium", "potassium", "calcium", "iron", "iodine", "zinc",
    "selenium", "vitaminA", "vitaminD", "vitaminB12", "folate", "vitaminC",
}
GRAM_NUTRIENTS = {
    "carbs", "protein", "fat", "fiber", "sugar", "saturatedFat",
    "polyunsaturatedFat",
}
MILLIGRAM_NUTRIENTS = {
    "sodium", "magnesium", "potassium", "calcium", "iron", "zinc",
    "vitaminC", "caffeine",
}
MICROGRAM_NUTRIENTS = {
    "iodine", "selenium", "vitaminA", "vitaminD", "vitaminB12", "folate",
}
MARKET_LANGUAGE_PREFERENCES = {
    "DE": ("de",),
    "AT": ("de",),
    "CH": ("de", "fr", "it"),
    "US": ("en",),
    "CA": ("en", "fr"),
    "GB": ("en",),
    "IE": ("en",),
    "AU": ("en",),
    "NZ": ("en",),
}
GERMAN_COMPOUND_EXPANSIONS = {
    "basmatireis": ("basmati", "reis"),
    "jasminreis": ("jasmin", "reis"),
    "jasminduftreis": ("jasmin", "reis"),
}


def normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_like = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.findall(r"[\w]+", ascii_like, flags=re.UNICODE))


def text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = " ".join(value.split()).strip()
    return result or None


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        values = [text(item) for item in value]
    elif isinstance(value, str):
        values = [text(item) for item in value.split(",")]
    else:
        return []
    return list(dict.fromkeys(item for item in values if item))


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def localized_values(record: dict[str, Any], field: str) -> dict[str, str]:
    """Return every OFF language-specific value using stable BCP-47-like keys."""
    pattern = re.compile(rf"^{re.escape(field)}_([A-Za-z]{{2,3}}(?:[_-][A-Za-z]{{2,4}})?)$")
    values: dict[str, str] = {}
    for key, value in record.items():
        match = pattern.fullmatch(key)
        if match and (resolved := text(value)):
            language = match.group(1).replace("_", "-").lower()
            values[language] = resolved
    return values


def preferred_field_value(record: dict[str, Any], field: str,
                          preferred_languages: Iterable[str] = ()) -> str | None:
    """Choose an explicitly market-localized value before generic fallbacks."""
    localized = localized_values(record, field)
    for language in preferred_languages:
        normalized_language = language.replace("_", "-").lower()
        if value := localized.get(normalized_language):
            return value
        regional_key = next((key for key in sorted(localized)
                             if key.startswith(f"{normalized_language}-")), None)
        if regional_key:
            return localized[regional_key]
    if value := text(record.get(field)):
        return value
    return next((localized[key] for key in sorted(localized)), None)


def localized_preference_rank(record: dict[str, Any], field: str,
                              preferred_languages: Iterable[str]) -> int:
    localized = localized_values(record, field)
    preferences = tuple(preferred_languages)
    for index, language in enumerate(preferences):
        normalized_language = language.replace("_", "-").lower()
        if normalized_language in localized or any(
                key.startswith(f"{normalized_language}-") for key in localized):
            return len(preferences) - index + 2

    source_language = normalized_text(record.get("lang")).replace(" ", "-")
    if text(record.get(field)):
        if any(source_language == language
               or source_language.startswith(f"{language}-")
               for language in preferences):
            return len(preferences) + 2
        return 1
    return 0


def finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def valid_gtin(code: str) -> bool:
    if not code.isdigit() or len(code) not in {8, 12, 13, 14}:
        return False
    digits = [int(item) for item in code]
    body = list(reversed(digits[:-1]))
    total = sum(value * (3 if index % 2 == 0 else 1)
                for index, value in enumerate(body))
    return (10 - total % 10) % 10 == digits[-1]


def product_name(record: dict[str, Any],
                 preferred_languages: Iterable[str] = ()) -> str | None:
    return preferred_field_value(record, "product_name", preferred_languages)


def generic_name(record: dict[str, Any],
                 preferred_languages: Iterable[str] = ()) -> str | None:
    return preferred_field_value(record, "generic_name", preferred_languages)


def product_categories(record: dict[str, Any]) -> list[str]:
    return string_list(record.get("categories"))


def product_category_tags(record: dict[str, Any]) -> list[str]:
    return string_list(record.get("categories_tags"))


def all_field_values(record: dict[str, Any], field: str) -> list[str]:
    values = [text(record.get(field)), *localized_values(record, field).values()]
    return list(dict.fromkeys(value for value in values if value))


def all_categories(record: dict[str, Any]) -> list[str]:
    values = product_categories(record)
    for localized in localized_values(record, "categories").values():
        values.extend(string_list(localized))
    return list(dict.fromkeys(values))


def search_aliases(value: str) -> list[str]:
    """Return normalized spaced, package-free and narrow compound variants."""
    bases = list(dict.fromkeys(filter(None, (
        normalized_text(value),
        normalized_text(family_name(value)),
    ))))
    aliases = list(bases)
    for base in bases:
        tokens = base.split()
        expanded = [part for token in tokens
                    for part in GERMAN_COMPOUND_EXPANSIONS.get(token, (token,))]
        if expanded != tokens:
            aliases.append(" ".join(expanded))
        # German food compounds are commonly entered both joined and spaced.
        # Limit generated forms to short phrases to avoid indexing whole label
        # sentences as low-value giant tokens.
        if 2 <= len(tokens) <= 4:
            compact = "".join(tokens)
            if len(compact) >= 6:
                aliases.append(compact)
    return list(dict.fromkeys(aliases))


def alcohol_classification(record: dict[str, Any]) -> str:
    identity_candidates = (
        list(localized_values(record, "product_name").values())
        + list(localized_values(record, "generic_name").values())
        + [value for value in (product_name(record), generic_name(record)) if value]
    )
    category_candidates = product_categories(record) + product_category_tags(record)
    normalized_identity = [normalized_text(value) for value in identity_candidates]
    normalized_categories = [
        normalized_text(re.sub(r"^[A-Za-z]{2,3}:", "", value))
        for value in category_candidates
    ]
    normalized = normalized_identity + normalized_categories
    nonalcoholic_phrases = (
        "alcohol free", "alcoholfree", "non alcohol", "non alcoholic",
        "nonalcoholic", "ohne alkohol", "sans alcool", "alkoholfrei",
    )
    if any(any(phrase in value for phrase in nonalcoholic_phrases)
           for value in normalized):
        return "nonAlcoholic"

    alcohol_terms = {
        "alcohol", "alcoholic", "beer", "beers", "bier", "cider",
        "liqueur", "liqueurs", "liquor", "rum",
        "spirit", "spirits", "vodka", "wein", "whisky", "whiskey",
        "wine", "wines",
    }
    cocktail_names = {
        "bloody mary", "caipirinha", "cosmopolitan", "daiquiri", "mai tai",
        "margarita", "mojito", "pina colada", "sex on the beach",
    }
    for value in normalized_categories:
        words = set(value.split())
        if value in {"cocktail", "cocktails"} or not words.isdisjoint(alcohol_terms):
            return "alcoholic"
    for value in normalized_identity:
        if value in cocktail_names:
            return "alcoholic"
    return "unknown"


def searchable_product_terms(record: dict[str, Any]) -> tuple[str, ...]:
    category_tags = [re.sub(r"^[A-Za-z]{2,3}:", "", value)
                     for value in product_category_tags(record)]
    values = (
        string_list(record.get("brands"))
        + all_field_values(record, "product_name")
        + all_field_values(record, "generic_name")
        + all_categories(record)
        + category_tags
        + search_names(product_category_tags(record))
    )
    terms = [alias for value in values for alias in search_aliases(value)]
    return tuple(dict.fromkeys(terms))


def brand_name(record: dict[str, Any]) -> str | None:
    brands = string_list(record.get("brands"))
    return brands[0] if brands else None


TEST_ENTRY_MARKERS = {
    "test", "tests", "testing", "testproduct", "testprodukt",
    "testentry", "testeintrag", "testfood", "testscan", "testbarcode",
    "testnutriscan",
}


# Rules that keep user test entries and other companies' menu items out of a
# market pack (b220, 30 October 2026). Every rejection is written to the
# market's sidecar, rejected-<code>.jsonl, with its rule, so a wrong one can be
# looked up; README.md lists the rules and the last run's counts.
ENERGY_PER_GRAM = {"protein": 4.0, "fat": 9.0, "carbs": 4.0, "fiber": 2.0, "alcohol": 7.0,
                   "polyols": 2.4, "organicAcids": 3.0}
ALCOHOL_GRAMS_PER_PERCENT_VOLUME = 0.789
# The rule constants, in one place; the live-search worker carries the same.
ENERGY_TOLERANCE_SHARE = 0.20          # rule 1: declared energy within 20 % of its components' energy
ENERGY_TOLERANCE_KCAL = 12.0           #         or within 12 kcal, whichever is larger
GRAM_CEILING_PER_100 = 100.0           # rule 1: no nutrient above 100 g per 100 g or ml
POPULARITY_FLOOR_COMPLETENESS = 0.5    # rule 3: an unbranded, unscanned record below this completeness is a stub
CHAIN_MATCH_MIN_CALORIES = 50.0        # rule 4: a menu item below this per 100 g never identifies a copy
CHAIN_MATCH_CALORIE_SHARE = 0.10       # rule 4: calories within 10 % of the chain's figure
CHAIN_MATCH_CALORIE_KCAL = 10.0        #         or within 10 kcal
CHAIN_MATCH_MACRO_SHARE = 0.15         # rule 4: fat, carbs and protein each within 15 %
CHAIN_MATCH_MACRO_GRAMS = 1.5          #         or within 1.5 g
PACK_RULE_NAMES = ("implausible-nutrition", "unscanned-unbranded", "chain-item-under-another-brand")
MENU_CLAIMS_FILE = Path(__file__).resolve().parent / "chains" / "menu-claims.json"
CHAIN_FILES = (
    tuple(sorted((Path(__file__).resolve().parent / "chains").glob("*.json")))
    + (Path(__file__).resolve().parent / "cafe" / "starbucks-de.json",)
)
GENERIC_NAME_FILES = (
    (Path(__file__).resolve().parent / "staples.json",),
    (Path(__file__).resolve().parent / "recipes" / "recipes.json",),
    tuple(path for path in sorted((Path(__file__).resolve().parent / "cafe").glob("*.json"))
          if path.name != "starbucks-de.json"),
)
MENU_NAME_STOPWORDS = {
    "short", "tall", "grande", "venti", "small", "medium", "large", "regular",
    "mini", "maxi", "xl", "xxl", "classic", "original", "menu", "meal", "klein",
    "mittel", "gross", "mit", "ohne", "und", "and", "with", "oder", "or", "the",
    "de", "la", "le", "au", "a", "l", "ml", "cl", "g", "kg", "st", "stk", "er",
    "x", "halbfettmilch", "vollmilch", "magermilch", "hafer", "mandel", "soja",
    "kokos", "haferdrink", "laktosefrei", "decaf", "iced", "hot", "blonde",
    "ristretto", "flavour", "geschmack", "style", "plant", "based", "vegan",
    "veggie", "double", "triple", "single", "footlong", "sub", "wrap", "bowl",
    "box", "pack", "portion", "set", "deluxe", "extra", "neu", "new",
}


GENERIC_MENU_WORDS = {
    # Café and counter words every maker uses; a chain's row with only these
    # names no product of its own.
    "americano", "espresso", "cappuccino", "latte", "macchiato", "mocha", "chai",
    "matcha", "cocoa", "kakao", "kaffee", "coffee", "tea", "tee", "smoothie",
    "lemonade", "limonade", "cooler", "shake", "milchshake", "milkshake",
    "ketchup", "mayo", "mayonnaise", "dip", "dips", "sauce", "sosse", "dressing",
    "sticks", "nuggets", "wings", "tenders", "fries", "pommes", "burger",
    "cheeseburger", "hamburger", "salat", "salad", "wrap", "sandwich", "baguette",
    "filet", "brezel", "breze", "brezn", "stange", "brot", "brotchen", "muffin",
    "cookie", "cookies", "bagel", "donut", "doughnut", "brownie", "scone",
    "croissant", "kuchen", "schnecke", "tasche", "taschen", "simit", "ciabatta",
    "panini", "toast", "toasty", "egg", "ei", "cheese", "kase", "bacon", "chicken",
    "hahnchen", "beef", "rind", "fish", "fisch", "veggie", "salmon", "lachs",
    "crispy", "crispys", "onion", "rings", "ring", "wasser", "water", "mineral",
    "sprudel", "cola", "orange", "apfel", "apple", "cherry", "kirsch", "lime",
    "limette", "lemon", "zitrone", "vanilla", "vanille", "caramel", "karamell",
    "chocolate", "schokolade", "schoko", "strawberry", "erdbeer", "erdbeere",
    "banana", "banane", "mango", "coconut", "kokos", "kokosnus", "hazelnut",
    "haselnuss", "pistachio", "pistazie", "oat", "soy", "almond", "zero", "sugar",
    "zucker", "light", "diet", "sweet", "chili", "spicy", "honig", "honey", "senf",
    "mustard", "bbq", "garlic", "knoblauch", "herb", "krauter", "pepper", "pfeffer",
    "crema", "brew", "cold", "doppio", "biscuit", "biscuits", "gingerbread",
    "brownies", "baguettes", "juice", "saft", "schorle", "einweg", "flasche",
    "natural", "naturell", "classic", "zuckerfrei", "alkoholfrei", "free", "range",
    "hand", "cooked", "crisps", "chips", "nacho", "potato", "kartoffel", "falafel",
    "avocado", "hummus", "mezze", "omelett", "omelette", "porridge", "granola",
    "yoghurt", "joghurt", "quark", "pancakes", "pancake", "waffle", "waffel",
    "maiskolben", "fischsuppe", "suppe", "soup", "eis", "ice", "cream", "sahne",
    "kakaogetrank", "gruntee", "aromatisierter", "fairtrade", "concentrate", "pot",
    "nuggets", "nugget", "tortilla", "quesadilla", "burrito", "taco", "pizza", "pasta",
    "caffe", "cafe", "balsamico", "balsamic", "vinaigrette", "mayonnaise", "aioli",
    "ketchup", "senf", "mustard", "sweet", "sour", "chili", "curry", "garlic", "ranch",
    "caesar", "joghurt", "yogurt", "milch", "milk", "wasser", "water", "tee", "tea",
    "schwarz", "black", "white", "weiss", "gruner", "green", "classic", "klassik",
    "original", "natur", "pur", "pure",
}
GENERIC_SUFFIXES = tuple(word for word in GENERIC_MENU_WORDS if len(word) >= 5)
QUANTITY_TOKEN = re.compile(r"^\d+(?:ml|cl|l|g|kg|er|x|st|stk)?$")


def normalized_tokens(value: Any) -> set[str]:
    return {token for token in normalized_text(value).split() if token and not QUANTITY_TOKEN.match(token)}


def generic_token(token: str, generic: frozenset[str]) -> bool:
    return (token in generic or token in GENERIC_MENU_WORDS
            or (len(token) > 7 and token.endswith(GENERIC_SUFFIXES)))


@functools.lru_cache(maxsize=1)
def generic_food_tokens() -> frozenset[str]:
    """Every word of the index's own generic food names: staples, recipes and
    the café's generic drinks; never the verified rows' aliases, which name
    chain items themselves ("Big Mac, McDonald's")."""
    tokens: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            tokens.update(normalized_tokens(value))
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in {"id", "rows", "references", "collections", "about", "policy", "version"}:
                    continue
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for path in (path for group in GENERIC_NAME_FILES for path in group):
        if path.exists():
            walk(json.loads(path.read_text(encoding="utf-8")))
    return frozenset(tokens)


@functools.lru_cache(maxsize=1)
def chain_menu_names() -> dict[str, str]:
    """Menu item names that belong to one chain, normalized, with the chain's
    normalized name. A name counts only when one of its words is no word of a
    generic food in the index (Big Mac, Whopper, Frappuccino, McNuggets),
    so a chain's "Coleslaw" or "Blueberry Muffin" never claims another maker's."""
    generic = generic_food_tokens()
    names: dict[str, tuple[str, dict[str, float]]] = {}
    for path in CHAIN_FILES:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        chain_name = payload.get("chain") or "Starbucks"
        chain = normalized_text(chain_name)
        for row in payload.get("rows", []):
            name = normalized_text(row.get("name"))
            tokens = normalized_tokens(name) - MENU_NAME_STOPWORDS
            if not tokens or all(generic_token(token, generic) for token in tokens):
                continue
            per100 = row.get("valuesPer100g") if isinstance(row.get("valuesPer100g"), dict) else {}
            values = {key: number for key in ("calories", "fat", "carbs", "protein")
                      if (number := finite(per100.get(key))) is not None}
            names[name] = (chain, values, path.stem, chain_name)
    return names


def menu_claims() -> dict[str, Any]:
    """The finished claim list of rule 4 for the live-search worker: every menu
    name that can identify a copy (generic names already left out, the four
    values per 100 g present and the item substantial), with its chain."""
    claims = []
    for name, (_, values, key, chain_name) in sorted(chain_menu_names().items()):
        if any(field not in values for field in ("calories", "fat", "carbs", "protein")):
            continue
        if values["calories"] < CHAIN_MATCH_MIN_CALORIES:
            continue
        claims.append({"name": name, "chainKey": key, "chain": chain_name,
                       "per100g": {field: values[field] for field in ("calories", "fat", "carbs", "protein")}})
    return {
        "format": 1,
        "about": ("Rule 4 of the market packs (build_index.py): a product whose normalized name equals or "
                  "begins with one of these menu names, whose per-100 g values match the chain's within the "
                  "tolerances below, whose brand is neither the chain nor named in the item, and that nobody has "
                  "scanned in the market, is another company's menu item and stays out. Names made only of "
                  "generic food words are already left out."),
        "rules": {
            "energyToleranceShare": ENERGY_TOLERANCE_SHARE, "energyToleranceKcal": ENERGY_TOLERANCE_KCAL,
            "gramCeilingPer100": GRAM_CEILING_PER_100, "popularityFloorCompleteness": POPULARITY_FLOOR_COMPLETENESS,
            "chainMatchMinCalories": CHAIN_MATCH_MIN_CALORIES, "chainMatchCalorieShare": CHAIN_MATCH_CALORIE_SHARE,
            "chainMatchCalorieKcal": CHAIN_MATCH_CALORIE_KCAL, "chainMatchMacroShare": CHAIN_MATCH_MACRO_SHARE,
            "chainMatchMacroGrams": CHAIN_MATCH_MACRO_GRAMS,
        },
        "claims": claims,
    }


def write_menu_claims(path: Path = MENU_CLAIMS_FILE) -> int:
    payload = menu_claims()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(payload["claims"])


def chain_item_claim(normalized_name: str) -> tuple[str, str, dict[str, float]] | None:
    """The chain menu name a product name equals or starts with, with its chain
    and the chain's published values per 100 g."""
    menu = chain_menu_names()
    if normalized_name in menu:
        return (normalized_name, *menu[normalized_name][:2])
    best = None
    for name, (chain, values, _, _) in menu.items():
        if normalized_name.startswith(name + " ") and (best is None or len(name) > len(best[0])):
            best = (name, chain, values)
    return best


def carries_chain_values(nutrients: dict[str, float], values: dict[str, float]) -> bool:
    """Whether a product's per-100 values are the chain's published ones: energy
    within 10 % or 10 kcal and each macro within 15 % or 1.5 g. A product that
    merely shares a menu item's name keeps its own label and stays."""
    if "calories" not in values or any(key not in values for key in ("fat", "carbs", "protein")):
        return False
    if values["calories"] < CHAIN_MATCH_MIN_CALORIES:
        # A drink's or dressing's few kilocalories match any other within the
        # tolerance; only a substantial item's values identify a copy.
        return False
    if any(nutrients.get(key) is None for key in ("calories", "fat", "carbs", "protein")):
        return False
    if abs(nutrients["calories"] - values["calories"]) > max(CHAIN_MATCH_CALORIE_KCAL,
                                                             CHAIN_MATCH_CALORIE_SHARE * values["calories"]):
        return False
    return all(abs(nutrients[key] - values[key]) <= max(CHAIN_MATCH_MACRO_GRAMS, CHAIN_MATCH_MACRO_SHARE * values[key])
               for key in ("fat", "carbs", "protein"))


def scan_count(record: dict[str, Any]) -> float:
    return max(finite(record.get("unique_scans_n")) or 0.0, finite(record.get("scans_n")) or 0.0)


def scanned_in_market(record: dict[str, Any], market: "Market") -> bool:
    code = market.code.lower()
    tags = string_list(record.get("popularity_tags"))
    if any(f"-{code}-scans" in normalized_text(tag).replace(" ", "-") for tag in tags):
        return True
    return scan_count(record) > 0 and not tags


def energy_components(product: "Product") -> dict[str, float] | None:
    """The energy-bearing components of a product per 100 g or ml: the four
    macros from the parsed nutrients, plus alcohol (% vol or g), polyols and
    organic acids as the record declares them. None when a macro is missing or
    an alcoholic product declares no alcohol, since its energy cannot be checked."""
    nutrients = product.nutrients
    if any(nutrients.get(key) is None for key in ("calories", "protein", "fat", "carbs")):
        return None
    raw = product.record.get("nutriments")
    if not isinstance(raw, dict):
        raw = product.record
    components = {key: nutrients.get(key, 0.0) for key in ("protein", "fat", "carbs", "fiber")}
    for key, name in (("alcohol", "alcohol"), ("polyols", "polyols"), ("organic-acids", "organicAcids")):
        value = next((number for suffix in ("_100ml", "_100g")
                      if (number := finite(raw.get(f"{key}{suffix}"))) is not None), None)
        if value is not None:
            components[name] = value
    if "alcohol" in components:
        unit = str(raw.get("alcohol_unit") or "% vol")
        if "%" in unit or "vol" in unit.casefold():
            components["alcohol"] *= ALCOHOL_GRAMS_PER_PERCENT_VOLUME
    elif alcohol_classification(product.record) == "alcoholic":
        return None
    if "polyols" in components:
        components["carbs"] = max(0.0, components["carbs"] - components["polyols"])
    return components


def calculated_energy(components: dict[str, float]) -> float:
    return sum(value * ENERGY_PER_GRAM[key] for key, value in components.items() if key in ENERGY_PER_GRAM)


def energy_fits_macros(product: "Product") -> tuple[bool, float] | None:
    """Whether declared energy fits its components at 4/9/4 kcal per g, 2 for
    fibre, 7 for alcohol, 2.4 for polyols and 3 for organic acids, within 20 %
    or 12 kcal, with the calculated figure; None when it cannot be checked."""
    components = energy_components(product)
    if components is None:
        return None
    calories = product.nutrients["calories"]
    calculated = calculated_energy(components)
    return abs(calculated - calories) <= max(ENERGY_TOLERANCE_KCAL, calories * ENERGY_TOLERANCE_SHARE), calculated


SUGAR_FREE_PHRASES = ("zuckerfrei", "sugar free", "sugarfree", "sans sucre", "senza zucchero",
                      "sin azucar", "ohne zucker", "suikervrij", "kaugummi", "chewing gum",
                      "polyol", "maltit", "sorbit", "xylit", "erythrit", "isomalt")


def energy_gap_explained(product: "Product", calculated: float) -> bool:
    """Whether a declared energy that misses the macronutrients' can still be
    right: a drink with more energy than its macros carry may hold alcohol or
    acids its record leaves out (wine, cider, vinegar); a sugar-free product
    with less energy than its carbohydrates imply sweetens with polyols it does
    not declare. Everything else is judged."""
    calories = product.nutrients["calories"]
    if calories > calculated:
        if product.nutrition_basis == "per100Milliliters":
            return True
        # A beverage declared per 100 g (beer, wine, cider) carries the same doubt.
        tags = " ".join(normalized_text(tag) for tag in string_list(product.record.get("categories_tags")))
        return any(word in tags for word in ("beverage", "drink", "getrank", "boisson", "beer", "bier", "wine", "wein", "cider", "alcohol"))
    haystack = " ".join(normalized_text(product.record.get(key)) for key in
                        ("product_name", "generic_name", "ingredients_text", "categories", "labels"))
    return any(phrase in haystack for phrase in SUGAR_FREE_PHRASES)


def rejection(product: "Product", market: "Market") -> tuple[str, str] | None:
    """The rule that keeps a parsed product out of a market pack, or None."""
    record = product.record
    nutrients = product.nutrients
    over = sorted(key for key in GRAM_NUTRIENTS if nutrients.get(key, 0) > GRAM_CEILING_PER_100)
    if over:
        return "implausible-nutrition", f"{', '.join(over)} above 100 g per 100"
    fit = energy_fits_macros(product)
    if fit is not None and not fit[0] and not energy_gap_explained(product, fit[1]):
        return "implausible-nutrition", (f"{nutrients['calories']:.0f} kcal declared, "
                                          f"{fit[1]:.0f} kcal from the macronutrients")
    completeness = finite(record.get("completeness")) or 0.0
    if not product.brand and scan_count(record) <= 0 and completeness < POPULARITY_FLOOR_COMPLETENESS:
        return "unscanned-unbranded", f"no brand, no scans, completeness {completeness:.2f}"
    claim = chain_item_claim(product.normalized_name) or chain_item_claim(normalized_text(product.name))
    if (claim and product.nutrition_basis == "per100Grams"
            and carries_chain_values(nutrients, claim[2])
            and not brand_is_chain(product.normalized_brand, claim[1])
            and not brand_names_item(product.normalized_brand, claim[0])
            and not scanned_in_market(record, market)):
        return "chain-item-under-another-brand", (f"'{claim[0]}' is a {claim[1]} menu item with its published values; "
                                                  f"brand {product.brand or 'none'}")
    return None


def brand_names_item(normalized_brand: str, menu_name: str) -> bool:
    """Whether the menu item is the brand's own product that the chain merely
    sells: a Coca-Cola or Pepsi row in a chain's file names its maker."""
    brand_tokens = set(normalized_brand.split()) - MENU_NAME_STOPWORDS
    return bool(brand_tokens) and not brand_tokens.isdisjoint(menu_name.split())


def brand_is_chain(normalized_brand: str, chain: str) -> bool:
    """Whether a product's brand names the chain: "McDonald's", "McDonalds" and
    "McDonald's Deutschland" all own a Big Mac."""
    chain_tokens = set(chain.split()) - {"deutschland", "germany", "uk", "de"}
    brand_tokens = set(normalized_brand.split())
    if chain_tokens and chain_tokens.issubset(brand_tokens):
        return True
    compact_chain = "".join(sorted(chain_tokens)) if len(chain_tokens) > 1 else "".join(chain_tokens)
    compact_brand = normalized_brand.replace(" ", "")
    return bool(compact_chain) and ("".join(chain.split()).replace("deutschland", "") in compact_brand
                                    or compact_chain in compact_brand)


def contains_test_entry_marker(value: str) -> bool:
    return not set(normalized_text(value).split()).isdisjoint(TEST_ENTRY_MARKERS)


def is_test_entry(record: dict[str, Any]) -> bool:
    name_is_test_entry = any(
        not set(normalized_text(name).split()).isdisjoint(TEST_ENTRY_MARKERS)
        for name in all_field_values(record, "product_name")
    )
    normalized_brand = normalized_text(brand_name(record) or "")
    brand_is_test_entry = contains_test_entry_marker(normalized_brand)
    if not name_is_test_entry and not brand_is_test_entry:
        return False
    return not (normalized_brand == "test" and not name_is_test_entry)


def nutrition_basis(record: dict[str, Any]) -> str:
    declared = normalized_text(record.get("nutrition_data_per"))
    units = {
        normalized_text(record.get("product_quantity_unit")),
        normalized_text(record.get("serving_quantity_unit")),
    }
    volume_units = {
        "ml", "milliliter", "milliliters", "millilitre", "millilitres",
        "l", "liter", "liters", "litre", "litres",
    }
    if "ml" in declared:
        return "per100Milliliters"
    if "g" in declared:
        identity = " ".join(normalized_text(value) for value in (
            all_field_values(record, "product_name")
            + all_field_values(record, "generic_name")
            + all_categories(record)
        ))
        dry_forms = {"powder", "pulver", "concentrate", "konzentrat", "syrup", "sirup"}
        explicitly_named_drink = re.search(
            r"\b\w*(?:getrank|schorle|shorle)\b", identity) is not None
        if (units.intersection(volume_units) and explicitly_named_drink
                and set(identity.split()).isdisjoint(dry_forms)):
            return "per100Milliliters"
        return "per100Grams"
    return "per100Milliliters" if units.intersection(volume_units) else "per100Grams"


def scaled_nutrients(record: dict[str, Any], basis: str) -> dict[str, float]:
    raw = record.get("nutriments")
    if not isinstance(raw, dict):
        raw = record
    result: dict[str, float] = {}
    for nutrient, keys in SUPPORTED_NUTRIENTS.items():
        preferred_keys = keys
        if basis == "per100Milliliters":
            preferred_keys = tuple(key.replace("_100g", "_100ml") for key in keys) + keys
        value = next((number for key in preferred_keys
                      if (number := finite(raw.get(key))) is not None), None)
        if value is None:
            continue
        if nutrient in MILLIGRAM_NUTRIENTS:
            value *= 1_000
        elif nutrient in MICROGRAM_NUTRIENTS:
            value *= 1_000_000
        result[nutrient] = round(value, 6)
    if "calories" not in result:
        energy_keys = (("energy-kj_100ml", "energy_100ml", "energy-kj_100g", "energy_100g")
                       if basis == "per100Milliliters"
                       else ("energy-kj_100g", "energy_100g"))
        kilojoules = next((number for key in energy_keys
                           if (number := finite(raw.get(key))) is not None), None)
        if kilojoules is not None:
            result["calories"] = round(kilojoules / 4.184, 6)
    if "sodium" not in result:
        salt_keys = ("salt_100ml", "salt_100g") if basis == "per100Milliliters" else ("salt_100g",)
        salt = next((v for key in salt_keys if (v := finite(raw.get(key))) is not None), None)
        if salt is not None:
            result["sodium"] = round(salt / 2.5 * 1000, 6)
    return result


def validation_issues(nutrients: dict[str, float], basis: str = "per100Grams") -> list[str]:
    issues: list[str] = []
    calories = nutrients.get("calories")
    if calories is None or calories <= 0 or calories > 1_000:
        issues.append("invalid-energy")
    for key in GRAM_NUTRIENTS:
        if basis == "per100Grams" and nutrients.get(key, 0) > 100:
            issues.append(f"invalid-{key}")
    macros = [nutrients.get(key) for key in ("protein", "fat", "carbs")]
    if calories and all(value is not None for value in macros):
        calculated = nutrients["protein"] * 4 + nutrients["fat"] * 9 + nutrients["carbs"] * 4
        if abs(calculated - calories) > max(80, calories * 0.35):
            issues.append("energy-macro-mismatch")
    if basis == "per100Grams" and all(value is not None for value in macros) and sum(macros) > 105:
        issues.append("macro-mass-exceeds-basis")
    for component, total in (("sugar", "carbs"), ("saturatedFat", "fat"), ("polyunsaturatedFat", "fat")):
        if component in nutrients and total in nutrients and nutrients[component] > nutrients[total] + 2:
            issues.append(component + "-exceeds-" + total)
    for key in MILLIGRAM_NUTRIENTS | MICROGRAM_NUTRIENTS:
        maximum = 100_000 if key in MILLIGRAM_NUTRIENTS else 100_000_000
        if basis == "per100Grams" and nutrients.get(key, 0) > maximum:
            issues.append("invalid-" + key)
    return issues


def family_name(name: str) -> str:
    """Remove package-size text that does not change the product identity."""
    without_multipacks = re.sub(
        r"\b(?:\d+(?:[.,]\d+)?\s*[x×]\s*)?\d+(?:[.,]\d+)?\s*"
        r"(?:mg|g|kg|ml|cl|dl|l|oz|lb|lbs)\b",
        " ", name, flags=re.IGNORECASE)
    return " ".join(without_multipacks.split()).strip(" -–—,·") or name


def family_identity(name: str, brand: str | None, barcode: str) -> tuple[str, str, str]:
    normalized_name = normalized_text(family_name(name))
    normalized_brand = normalized_text(brand)
    # Upstream alternates between names such as "Classic" and "Fol Epi
    # Classic" while carrying the same Fol Epi brand. A repeated leading brand
    # is presentation, not a distinct product identity.
    brand_prefix = f"{normalized_brand} "
    if normalized_brand and normalized_name.startswith(brand_prefix):
        without_brand = normalized_name[len(brand_prefix):].strip()
        if without_brand:
            normalized_name = without_brand
    # Products without a brand are too ambiguous to merge automatically.
    family_key = f"{normalized_brand}|{normalized_name}" if normalized_brand else f"{barcode}|{normalized_name}"
    return family_key, normalized_name, normalized_brand


def source_hash(record: dict[str, Any]) -> str:
    fields = {
        "code", "product_name", "product_name_en", "product_name_de", "brands",
        "generic_name", "generic_name_en", "generic_name_de", "categories",
        "categories_tags", "lang",
        "last_modified_t", "completeness", "serving_size", "serving_quantity",
        "serving_quantity_unit", "nutrition_data_per", "product_quantity_unit",
        "image_url", "image_small_url",
        "image_front_url", "image_front_small_url", "nutriscore_grade",
        "nutrition_grades", "nova_group", "nutrient_levels",
        "nutrient_levels_tags", "data_quality_errors_tags",
        "data_quality_warnings_tags", "nutriments", "nutrition", "_akari_nutrition_provenance",
        *SUPPORTED_NUTRIENTS.values(),
    }
    flattened = set()
    for value in fields:
        if isinstance(value, tuple):
            flattened.update(value)
        else:
            flattened.add(value)
    flattened.update(key.replace("_100g", "_100ml") for key in tuple(flattened))
    flattened.update({"energy-kj_100ml", "energy_100ml"})
    flattened.update(
        key for key in record
        if key.startswith(("product_name_", "generic_name_", "categories_"))
    )
    projection = {
        key: record[key] for key in flattened
        if key in record and record[key] not in (None, "", [], {})
    }
    encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def market_tags(record: dict[str, Any]) -> set[str]:
    return {normalized_text(tag).replace(" ", "-") for tag in string_list(record.get("countries_tags"))}


def serving(record: dict[str, Any]) -> tuple[
        float | None, str | None, float | None, float | None, str | None]:
    if not accepts_serving_label(text(record.get("serving_size")), text(record.get("product_name")),
                   text(record.get("generic_name"))):
        return None, None, None, None, None
    amount = finite(record.get("serving_quantity"))
    unit = normalized_text(record.get("serving_quantity_unit"))
    grams: float | None = None
    milliliters: float | None = None
    if amount is not None:
        if unit in {"g", "gram", "grams"}:
            grams = amount
        elif unit in {"kg", "kilogram", "kilograms"}:
            grams = amount * 1_000
        elif unit in {"ml", "milliliter", "milliliters", "millilitre", "millilitres"}:
            milliliters = amount
        elif unit in {"l", "liter", "liters", "litre", "litres"}:
            milliliters = amount * 1_000
    return amount, unit or None, grams, milliliters, text(record.get("serving_size"))


def serving_quality(record: dict[str, Any]) -> tuple[int, int, int]:
    amount, unit, grams, milliliters, label = serving(record)
    converted_amount = grams if grams is not None else milliliters
    return (
        int(converted_amount is not None and converted_amount > 0),
        int(amount is not None and amount > 0 and unit is not None),
        int(label is not None),
    )


def core_nutrition_quality(nutrients: dict[str, float],
                           validation: list[str]) -> tuple[int, int]:
    valid_macro_count = sum(
        1 for nutrient in ("protein", "fat", "carbs")
        if (value := nutrients.get(nutrient)) is not None and 0 <= value <= 100
    )
    invalid_core = "energy-macro-mismatch" in validation or any(
        issue in validation
        for issue in ("invalid-protein", "invalid-fat", "invalid-carbs")
    )
    # Energy is mandatory before a Product is created. Clean records then rank
    # by useful macro coverage; inconsistent macro labels rank below them all.
    grade = 0 if invalid_core else valid_macro_count + 1
    return grade, valid_macro_count


def product_image(record: dict[str, Any]) -> str | None:
    return text(record.get("image_url") or record.get("image_front_url")
                or record.get("image_small_url") or record.get("image_front_small_url"))


def nutrient_levels(record: dict[str, Any]) -> dict[str, str]:
    raw = record.get("nutrient_levels")
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    result: dict[str, str] = {}
    for tag in string_list(record.get("nutrient_levels_tags")):
        normalized = tag.removeprefix("en:")
        for nutrient in ("fat", "saturated-fat", "sugars", "salt"):
            prefix = f"{nutrient}-in-"
            suffix = "-quantity"
            if normalized.startswith(prefix) and normalized.endswith(suffix):
                level = normalized[len(prefix):-len(suffix)]
                if level in {"low", "moderate", "high"}:
                    result[nutrient] = level
    return result


@dataclass(frozen=True)
class Market:
    code: str
    country_tag: str

    @property
    def language_preferences(self) -> tuple[str, ...]:
        return MARKET_LANGUAGE_PREFERENCES.get(self.code, ("en",))

    @classmethod
    def parse(cls, value: str) -> "Market":
        code, separator, tag = value.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z]{2}(?:-[A-Za-z]{3})?", code):
            raise argparse.ArgumentTypeError("market must look like DE=en:germany")
        normalized_tag = normalized_text(tag).replace(" ", "-")
        if not normalized_tag:
            raise argparse.ArgumentTypeError("market country tag cannot be empty")
        return cls(code.upper(), normalized_tag)


@dataclass
class Product:
    barcode: str
    name: str
    brand: str | None
    family_key: str
    normalized_name: str
    normalized_brand: str
    nutrition_basis: str
    nutrients: dict[str, float]
    validation: list[str]
    quality_score: int
    source_modified_at: int | None
    source_hash: str
    search_terms: tuple[str, ...]
    record: dict[str, Any] = field(repr=False)

    def for_market(self, market: Market) -> "Product":
        name = product_name(self.record, market.language_preferences) or self.name
        _, normalized_name, normalized_brand = family_identity(
            name, self.brand, self.barcode)
        # Family identity follows OFF's primary product name so localized
        # spellings do not split package variants into separate families. The
        # displayed/search-ranked name, however, follows the selected market.
        return replace(self, name=name,
                       normalized_name=normalized_name,
                       normalized_brand=normalized_brand)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Product | None":
        record = normalize_record(record)
        barcode = str(record.get("code") or "").strip()
        name = product_name(record)
        if not valid_gtin(barcode) or not name or is_test_entry(record):
            return None
        basis = nutrition_basis(record)
        nutrients = scaled_nutrients(record, basis)
        validation = validation_issues(nutrients, basis)
        if "invalid-energy" in validation:
            return None
        brand = brand_name(record)
        family_key, normalized_name, normalized_brand = family_identity(name, brand, barcode)
        quality_errors = len(string_list(record.get("data_quality_errors_tags")))
        quality_warnings = len(string_list(record.get("data_quality_warnings_tags")))
        completeness = finite(record.get("completeness")) or 0
        micro_count = len(MICRONUTRIENTS.intersection(nutrients))
        nutrition_grade, _ = core_nutrition_quality(nutrients, validation)
        serving_rank = serving_quality(record)
        serving_score = serving_rank[0] * 3 + serving_rank[1] * 2 + serving_rank[2]
        score = (
            nutrition_grade * 10_000
            + serving_score * 1_000
            + round(min(completeness, 1) * 100)
            + len(nutrients) * 10
            + micro_count * 5
            + (25 if product_image(record) else 0)
            - quality_errors * 50_000
            - quality_warnings * 100
            - len(validation) * 10_000
        )
        modified = finite(record.get("last_modified_t"))
        return cls(barcode, name, brand, family_key, normalized_name,
                   normalized_brand, basis, nutrients, validation, score,
                   int(modified) if modified is not None else None,
                   source_hash(record), searchable_product_terms(record), record)


def representative_rank(product: Product, market: Market,
                        sku_id: int) -> tuple[Any, ...]:
    record = product.record
    quality_errors = len(string_list(record.get("data_quality_errors_tags")))
    quality_warnings = len(string_list(record.get("data_quality_warnings_tags")))
    completeness = min(finite(record.get("completeness")) or 0, 1)
    locale_rank = (
        localized_preference_rank(
            record, "product_name", market.language_preferences),
        localized_preference_rank(
            record, "generic_name", market.language_preferences),
    )
    return (
        core_nutrition_quality(product.nutrients, product.validation),
        -quality_errors,
        -len(product.validation),
        serving_quality(record),
        locale_rank,
        product.source_modified_at or 0,
        -quality_warnings,
        len(MICRONUTRIENTS.intersection(product.nutrients)),
        len(product.nutrients),
        completeness,
        int(product_image(record) is not None),
        -sku_id,
    )


class IndexWriter:
    def __init__(self, path: Path, market: Market, generated_at: str, schema: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        self.path = path
        self.market = market
        self.generated_at = generated_at
        self.connection = sqlite3.connect(path)
        self.connection.executescript(schema)
        self.connection.execute(
            """CREATE TEMP TABLE family_search_term(
                family_id INTEGER NOT NULL,
                term TEXT NOT NULL,
                PRIMARY KEY(family_id, term)
            ) WITHOUT ROWID""")
        self.family_ids: dict[str, int] = {}
        self.best_sku: dict[int, tuple[Any, ...]] = {}
        self.product_count = 0

    def add(self, product: Product) -> None:
        product = product.for_market(self.market)
        record = product.record
        family_id = self.family_ids.get(product.family_key)
        if family_id is None:
            cursor = self.connection.execute(
                """INSERT INTO family(
                    family_key, canonical_name, canonical_brand,
                    normalized_name, normalized_brand, variant_count
                ) VALUES (?, ?, ?, ?, ?, 0)""",
                (product.family_key, product.name, product.brand,
                 product.normalized_name, product.normalized_brand))
            family_id = int(cursor.lastrowid)
            self.family_ids[product.family_key] = family_id

        serving_amount, serving_unit, serving_grams, serving_milliliters, serving_label = serving(record)
        levels = nutrient_levels(record)
        completeness = finite(record.get("completeness"))
        nova = finite(record.get("nova_group"))
        cursor = self.connection.execute(
            """INSERT INTO sku(
                family_id, barcode, product_name, brand, market,
                nutrition_basis, serving_amount, serving_unit,
                serving_grams, serving_milliliters, serving_label, image_url,
                nutri_score, nova_group, nutrient_levels_json, calories,
                nutrients_json, localized_names_json, generic_name,
                localized_generic_names_json, categories_json,
                category_tags_json, alcohol_classification, artwork_classification_json,
                nutrient_count, micronutrient_count, completeness, quality_score,
                source_modified_at, record_hash, validation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(barcode) DO UPDATE SET
                family_id=excluded.family_id,
                product_name=excluded.product_name,
                brand=excluded.brand,
                market=excluded.market,
                nutrition_basis=excluded.nutrition_basis,
                serving_amount=excluded.serving_amount,
                serving_unit=excluded.serving_unit,
                serving_grams=excluded.serving_grams,
                serving_milliliters=excluded.serving_milliliters,
                serving_label=excluded.serving_label,
                image_url=excluded.image_url,
                nutri_score=excluded.nutri_score,
                nova_group=excluded.nova_group,
                nutrient_levels_json=excluded.nutrient_levels_json,
                calories=excluded.calories,
                nutrients_json=excluded.nutrients_json,
                localized_names_json=excluded.localized_names_json,
                generic_name=excluded.generic_name,
                localized_generic_names_json=excluded.localized_generic_names_json,
                categories_json=excluded.categories_json,
                category_tags_json=excluded.category_tags_json,
                alcohol_classification=excluded.alcohol_classification,
                artwork_classification_json=excluded.artwork_classification_json,
                nutrient_count=excluded.nutrient_count,
                micronutrient_count=excluded.micronutrient_count,
                completeness=excluded.completeness,
                quality_score=excluded.quality_score,
                source_modified_at=excluded.source_modified_at,
                record_hash=excluded.record_hash,
                validation_json=excluded.validation_json
            WHERE excluded.quality_score > sku.quality_score
               OR (excluded.quality_score = sku.quality_score
                   AND COALESCE(excluded.source_modified_at, 0) > COALESCE(sku.source_modified_at, 0))
            RETURNING id""",
            (
                family_id, product.barcode, product.name, product.brand,
                self.market.code, product.nutrition_basis,
                serving_amount, serving_unit, serving_grams, serving_milliliters,
                serving_label, product_image(record),
                text(record.get("nutriscore_grade") or record.get("nutrition_grades")),
                int(nova) if nova is not None else None,
                compact_json(levels),
                product.nutrients["calories"],
                compact_json(product.nutrients),
                compact_json(localized_values(record, "product_name")),
                generic_name(record, self.market.language_preferences),
                compact_json(localized_values(record, "generic_name")),
                compact_json(product_categories(record)),
                compact_json(product_category_tags(record)),
                alcohol_classification(record),
                compact_json(classify(product.name, product.brand,
                                     generic_name(record, self.market.language_preferences),
                                     product_category_tags(record), product_categories(record)) or {}),
                len(product.nutrients), len(MICRONUTRIENTS.intersection(product.nutrients)),
                completeness, product.quality_score, product.source_modified_at,
                product.source_hash, compact_json(product.validation),
            ))
        returned = cursor.fetchone()
        if returned is None:
            existing = self.connection.execute(
                "SELECT id, family_id FROM sku WHERE barcode = ?", (product.barcode,)).fetchone()
            if existing is None:
                return
            sku_id, actual_family_id = int(existing[0]), int(existing[1])
            family_id = actual_family_id
        else:
            sku_id = int(returned[0])

        self.product_count += 1
        if self.product_count % 25_000 == 0:
            self.connection.commit()
        self.connection.executemany(
            "INSERT OR IGNORE INTO family_search_term(family_id, term) VALUES (?, ?)",
            ((family_id, term) for term in product.search_terms))

        rank = representative_rank(product, self.market, sku_id)
        if family_id not in self.best_sku or rank > self.best_sku[family_id]:
            self.best_sku[family_id] = rank
            self.connection.execute(
                """UPDATE family SET representative_sku_id = ?, canonical_name = ?,
                    canonical_brand = ?, normalized_name = ?, normalized_brand = ?
                    WHERE id = ?""",
                (sku_id, product.name, product.brand, product.normalized_name,
                 product.normalized_brand, family_id))

    def finish(self) -> dict[str, Any]:
        self.connection.execute(
            "DELETE FROM family WHERE NOT EXISTS "
            "(SELECT 1 FROM sku WHERE sku.family_id = family.id)")
        self.connection.execute(
            """UPDATE family SET variant_count = (
                SELECT COUNT(*) FROM sku WHERE sku.family_id = family.id)""")
        self.connection.execute(
            """INSERT INTO family_search(rowid, searchable)
               SELECT family_id, GROUP_CONCAT(term, ' ')
               FROM (
                   SELECT family_id, term
                   FROM family_search_term
                   ORDER BY family_id, term
               )
               GROUP BY family_id""")
        metadata = {
            "schemaVersion": str(SCHEMA_VERSION),
            "artworkClassificationVersion": str(CLASSIFICATION_VERSION),
            "catalogVersion": self.generated_at,
            "generatedAt": self.generated_at,
            "market": self.market.code,
            "countryTag": self.market.country_tag,
            "source": "Open Food Facts",
            "license": "ODbL 1.0",
        }
        self.connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
        family_count = self.connection.execute("SELECT COUNT(*) FROM family").fetchone()[0]
        sku_count = self.connection.execute("SELECT COUNT(*) FROM sku").fetchone()[0]
        self.connection.commit()
        self.connection.execute("ANALYZE")
        self.connection.execute("VACUUM")
        self.connection.close()
        digest = sha256_file(self.path)
        return {
            "market": self.market.code,
            "countryTag": self.market.country_tag,
            "filename": self.path.name,
            "sha256": digest,
            "bytes": self.path.stat().st_size,
            "familyCount": family_count,
            "skuCount": sku_count,
        }


def open_export(path: Path, *, gzip_input: bool = False,
                stream: Any = None) -> Iterator[dict[str, Any]]:
    """Read an export from disk or JSONL from stdin without buffering it."""
    if path == Path("-"):
        binary_stream = stream if stream is not None else sys.stdin.buffer
        handle = (gzip.open(binary_stream, "rt", encoding="utf-8", errors="replace")
                  if gzip_input
                  else io.TextIOWrapper(binary_stream, encoding="utf-8",
                                        errors="replace"))
        context = contextlib.nullcontext(handle)
    else:
        handle = (gzip.open(path, "rt", encoding="utf-8", errors="replace")
                  if path.suffix == ".gz"
                  else path.open("r", encoding="utf-8", errors="replace"))
        context = handle
    with context:
        if path.name.endswith(".csv") or path.name.endswith(".csv.gz"):
            # Ingredient and packaging fields can exceed Python's conservative
            # 128 KiB CSV default even though the compact index ignores most
            # of that text.
            csv.field_size_limit(16 * 1024 * 1024)
            yield from csv.DictReader(handle, delimiter="\t")
            return
        for line_number, line in enumerate(handle, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON on line {line_number}")
                continue
            if isinstance(value, dict):
                yield value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(output: Path, generated_at: str,
                   results: list[dict[str, Any]], base_url: str) -> None:
    markets = {
        result["market"]: {
            **result,
            "url": f"{base_url.rstrip('/')}/{result['filename']}",
        }
        for result in results
    }
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "catalogVersion": generated_at,
        "generatedAt": generated_at,
        "attribution": "Open Food Facts",
        "license": "ODbL 1.0",
        "markets": markets,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--menu-claims", type=Path, nargs="?", const=MENU_CLAIMS_FILE, default=None,
                        help="write rule 4's finished claim list for the live-search worker to this file "
                             "(default FoodIndex/chains/menu-claims.json) and stop")
    parser.add_argument("--off-export", "--off-jsonl", dest="off_export", type=Path)
    parser.add_argument("--off-export-gzip", action="store_true",
                        help="Decompress a gzip export streamed on stdin")
    parser.add_argument("--market", action="append", type=Market.parse)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--schema", type=Path,
                        default=Path(__file__).with_name("schema.sql"))
    parser.add_argument("--base-url", default=(
        "https://github.com/hejrafa/AkariFoodIndex/releases/latest/download"))
    parser.add_argument("--catalog-version")
    parser.add_argument("--allow-legacy-csv-for-audit", action="store_true", help="Audit only: CSV loses reported-versus-estimated provenance")
    args = parser.parse_args()
    if args.menu_claims is not None:
        print(f"Wrote {write_menu_claims(args.menu_claims):,} menu claims to {args.menu_claims}")
        return
    if args.off_export is None or not args.market or args.output_dir is None:
        parser.error("--off-export, --market and --output-dir are required to build market packs")
    if args.off_export.name.endswith((".csv", ".csv.gz")) and not args.allow_legacy_csv_for_audit:
        parser.error("Use the official JSONL export. CSV mixes reported and estimated nutrient values without provenance.")

    generated_at = args.catalog_version or dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")
    schema = args.schema.read_text(encoding="utf-8")
    writers = {
        market.code: IndexWriter(
            args.output_dir / f"akari-food-{market.code.lower()}.sqlite",
            market, generated_at, schema)
        for market in args.market
    }
    for writer in writers.values():
        writer.connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('nutrition_provenance',?)",
            ("unverified-flat-csv" if args.allow_legacy_csv_for_audit else "reported-json-input-sets",))
    accepted = 0
    rejections: dict[str, Counter[str]] = {market.code: Counter() for market in args.market}
    sidecars = {
        market.code: (args.output_dir / f"rejected-{market.code.lower()}.jsonl").open("w", encoding="utf-8")
        for market in args.market
    }
    try:
        for scanned, record in enumerate(open_export(
                args.off_export, gzip_input=args.off_export_gzip), 1):
            if scanned % 100_000 == 0:
                print(f"Scanned {scanned:,} source records; retained {accepted:,} market products", flush=True)
            if not args.allow_legacy_csv_for_audit and not (
                isinstance(record.get("nutrition"), dict) or isinstance(record.get("nutriments"), dict)
            ):
                continue
            tags = market_tags(record)
            if not any(market.country_tag in tags for market in args.market):
                continue
            product = Product.from_record(record)
            if product is None:
                continue
            tags = market_tags(record)
            matched = False
            for market in args.market:
                if market.country_tag in tags:
                    rejected = rejection(product, market)
                    if rejected:
                        rule, detail = rejected
                        rejections[market.code][rule] += 1
                        sidecars[market.code].write(json.dumps(
                            {"code": product.barcode, "name": product.name, "brand": product.brand,
                             "rule": rule, "detail": detail}, ensure_ascii=False) + "\n")
                        continue
                    writers[market.code].add(product)
                    matched = True
            accepted += int(matched)
    except BaseException:
        for writer in writers.values():
            with contextlib.suppress(Exception):
                writer.connection.close()
        raise
    finally:
        for sidecar in sidecars.values():
            sidecar.close()

    results = [writers[market.code].finish() for market in args.market]
    for result in results:
        result["rejected"] = dict(sorted(rejections[result["market"]].items()))
        result["rejectedFilename"] = f"rejected-{result['market'].lower()}.jsonl"
    write_manifest(args.output_dir / "manifest.json", generated_at,
                   results, args.base_url)
    (args.output_dir / "rejections.json").write_text(json.dumps(
        {"generatedAt": generated_at,
         "rules": list(PACK_RULE_NAMES),
         "markets": {code: dict(sorted(counts.items())) for code, counts in rejections.items()}},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Accepted {accepted:,} market product records")
    for code, counts in rejections.items():
        print(f"{code}: rejected " + (", ".join(f"{n:,} {rule}" for rule, n in sorted(counts.items())) or "nothing"))
    for result in results:
        print(f"{result['market']}: {result['familyCount']:,} families, "
              f"{result['skuCount']:,} SKUs, {result['bytes'] / 1_048_576:.1f} MiB")


if __name__ == "__main__":
    main()
