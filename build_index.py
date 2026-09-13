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


def nutrition_basis(record: dict[str, Any]) -> str:
    declared = normalized_text(record.get("nutrition_data_per"))
    if "ml" in declared:
        return "per100Milliliters"
    if "g" in declared:
        return "per100Grams"
    units = {
        normalized_text(record.get("product_quantity_unit")),
        normalized_text(record.get("serving_quantity_unit")),
    }
    volume_units = {
        "ml", "milliliter", "milliliters", "millilitre", "millilitres",
        "l", "liter", "liters", "litre", "litres",
    }
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
        if not valid_gtin(barcode) or not name:
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
    parser.add_argument("--off-export", "--off-jsonl", dest="off_export",
                        required=True, type=Path)
    parser.add_argument("--off-export-gzip", action="store_true",
                        help="Decompress a gzip export streamed on stdin")
    parser.add_argument("--market", action="append", required=True, type=Market.parse)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--schema", type=Path,
                        default=Path(__file__).with_name("schema.sql"))
    parser.add_argument("--base-url", default=(
        "https://github.com/hejrafa/AkariFoodIndex/releases/latest/download"))
    parser.add_argument("--catalog-version")
    parser.add_argument("--allow-legacy-csv-for-audit", action="store_true", help="Audit only: CSV loses reported-versus-estimated provenance")
    args = parser.parse_args()
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
                    writers[market.code].add(product)
                    matched = True
            accepted += int(matched)
    except BaseException:
        for writer in writers.values():
            with contextlib.suppress(Exception):
                writer.connection.close()
        raise

    results = [writers[market.code].finish() for market in args.market]
    write_manifest(args.output_dir / "manifest.json", generated_at,
                   results, args.base_url)
    print(f"Accepted {accepted:,} market product records")
    for result in results:
        print(f"{result['market']}: {result['familyCount']:,} families, "
              f"{result['skuCount']:,} SKUs, {result['bytes'] / 1_048_576:.1f} MiB")


if __name__ == "__main__":
    main()
