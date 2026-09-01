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
import json
import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = 1
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


def product_name(record: dict[str, Any]) -> str | None:
    for key in ("product_name", "product_name_en", "product_name_de"):
        if result := text(record.get(key)):
            return result
    return None


def brand_name(record: dict[str, Any]) -> str | None:
    brands = string_list(record.get("brands"))
    return brands[0] if brands else None


def scaled_nutrients(record: dict[str, Any]) -> dict[str, float]:
    raw = record.get("nutriments")
    if not isinstance(raw, dict):
        raw = record
    result: dict[str, float] = {}
    for nutrient, keys in SUPPORTED_NUTRIENTS.items():
        value = next((number for key in keys if (number := finite(raw.get(key))) is not None), None)
        if value is None:
            continue
        if nutrient in MILLIGRAM_NUTRIENTS:
            value *= 1_000
        elif nutrient in MICROGRAM_NUTRIENTS:
            value *= 1_000_000
        result[nutrient] = round(value, 6)
    if "calories" not in result:
        kilojoules = finite(raw.get("energy-kj_100g") or raw.get("energy_100g"))
        if kilojoules is not None:
            result["calories"] = round(kilojoules / 4.184, 6)
    return result


def validation_issues(nutrients: dict[str, float]) -> list[str]:
    issues: list[str] = []
    calories = nutrients.get("calories")
    if calories is None or calories <= 0 or calories > 1_000:
        issues.append("invalid-energy")
    for key in GRAM_NUTRIENTS:
        if nutrients.get(key, 0) > 100:
            issues.append(f"invalid-{key}")
    macros = [nutrients.get(key) for key in ("protein", "fat", "carbs")]
    if calories and all(value is not None for value in macros):
        calculated = nutrients["protein"] * 4 + nutrients["fat"] * 9 + nutrients["carbs"] * 4
        if abs(calculated - calories) > max(80, calories * 0.35):
            issues.append("energy-macro-mismatch")
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
        "last_modified_t", "completeness", "serving_size", "serving_quantity",
        "serving_quantity_unit", "image_url", "image_small_url",
        "image_front_url", "image_front_small_url", "nutriscore_grade",
        "nutrition_grades", "nova_group", "nutrient_levels",
        "nutrient_levels_tags", "data_quality_errors_tags",
        "data_quality_warnings_tags", "nutriments",
        *SUPPORTED_NUTRIENTS.values(),
    }
    flattened = set()
    for value in fields:
        if isinstance(value, tuple):
            flattened.update(value)
        else:
            flattened.add(value)
    projection = {
        key: record[key] for key in flattened
        if key in record and record[key] not in (None, "", [], {})
    }
    encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def market_tags(record: dict[str, Any]) -> set[str]:
    return {normalized_text(tag).replace(" ", "-") for tag in string_list(record.get("countries_tags"))}


def serving(record: dict[str, Any]) -> tuple[float | None, str | None]:
    grams = finite(record.get("serving_quantity"))
    unit = normalized_text(record.get("serving_quantity_unit"))
    if grams is not None and unit and unit not in {"g", "gram", "grams"}:
        grams = None
    return grams, text(record.get("serving_size"))


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
    nutrients: dict[str, float]
    validation: list[str]
    quality_score: int
    source_modified_at: int | None
    source_hash: str
    record: dict[str, Any] = field(repr=False)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Product | None":
        barcode = str(record.get("code") or "").strip()
        name = product_name(record)
        if not valid_gtin(barcode) or not name:
            return None
        nutrients = scaled_nutrients(record)
        validation = validation_issues(nutrients)
        if "invalid-energy" in validation:
            return None
        brand = brand_name(record)
        family_key, normalized_name, normalized_brand = family_identity(name, brand, barcode)
        quality_errors = len(string_list(record.get("data_quality_errors_tags")))
        quality_warnings = len(string_list(record.get("data_quality_warnings_tags")))
        completeness = finite(record.get("completeness")) or 0
        micro_count = len(MICRONUTRIENTS.intersection(nutrients))
        score = (
            micro_count * 1_000
            + len(nutrients) * 50
            + round(min(completeness, 1) * 100)
            + (25 if product_image(record) else 0)
            - quality_errors * 500
            - quality_warnings * 25
            - len(validation) * 100
        )
        modified = finite(record.get("last_modified_t"))
        return cls(barcode, name, brand, family_key, normalized_name,
                   normalized_brand, nutrients, validation, score,
                   int(modified) if modified is not None else None,
                   source_hash(record), record)


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
        self.family_ids: dict[str, int] = {}
        self.best_sku: dict[int, tuple[int, int, int]] = {}
        self.product_count = 0

    def add(self, product: Product) -> None:
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

        grams, serving_label = serving(record)
        levels = nutrient_levels(record)
        completeness = finite(record.get("completeness"))
        nova = finite(record.get("nova_group"))
        cursor = self.connection.execute(
            """INSERT INTO sku(
                family_id, barcode, product_name, brand, market,
                serving_grams, serving_label, image_url,
                nutri_score, nova_group, nutrient_levels_json, calories,
                nutrient_count, micronutrient_count, completeness, quality_score,
                source_modified_at, record_hash, validation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(barcode) DO UPDATE SET
                family_id=excluded.family_id,
                product_name=excluded.product_name,
                brand=excluded.brand,
                market=excluded.market,
                serving_grams=excluded.serving_grams,
                serving_label=excluded.serving_label,
                image_url=excluded.image_url,
                nutri_score=excluded.nutri_score,
                nova_group=excluded.nova_group,
                nutrient_levels_json=excluded.nutrient_levels_json,
                calories=excluded.calories,
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
                self.market.code, grams, serving_label, product_image(record),
                text(record.get("nutriscore_grade") or record.get("nutrition_grades")),
                int(nova) if nova is not None else None,
                json.dumps(levels, ensure_ascii=False, sort_keys=True),
                product.nutrients["calories"],
                len(product.nutrients), len(MICRONUTRIENTS.intersection(product.nutrients)),
                completeness, product.quality_score, product.source_modified_at,
                product.source_hash, json.dumps(product.validation),
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
        rank = (product.quality_score, product.source_modified_at or 0, -sku_id)
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
                SELECT id, TRIM(COALESCE(canonical_brand, '') || ' ' || canonical_name)
                FROM family""")
        metadata = {
            "schemaVersion": str(SCHEMA_VERSION),
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


def open_export(path: Path) -> Iterator[dict[str, Any]]:
    handle = (gzip.open(path, "rt", encoding="utf-8", errors="replace")
              if path.suffix == ".gz"
              else path.open("r", encoding="utf-8", errors="replace"))
    with handle:
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
    parser.add_argument("--market", action="append", required=True, type=Market.parse)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--schema", type=Path,
                        default=Path(__file__).with_name("schema.sql"))
    parser.add_argument("--base-url", default=(
        "https://github.com/hejrafa/AkariFoodIndex/releases/latest/download"))
    parser.add_argument("--catalog-version")
    args = parser.parse_args()

    generated_at = args.catalog_version or dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")
    schema = args.schema.read_text(encoding="utf-8")
    writers = {
        market.code: IndexWriter(
            args.output_dir / f"akari-food-{market.code.lower()}.sqlite",
            market, generated_at, schema)
        for market in args.market
    }
    accepted = 0
    try:
        for record in open_export(args.off_export):
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
