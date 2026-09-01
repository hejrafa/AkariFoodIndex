#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def record(code: str, name: str, calories: float, calcium: float,
           *, brand: str = "Fol Epi", modified: int = 1,
           countries: list[str] | None = None) -> dict:
    return {
        "code": code,
        "product_name": name,
        "brands": brand,
        "countries_tags": countries or ["en:germany"],
        "last_modified_t": modified,
        "completeness": 0.8,
        "nutriments": {
            "energy-kcal_100g": calories,
            "proteins_100g": 24,
            "fat_100g": 29,
            "carbohydrates_100g": 0.5,
            "calcium_100g": calcium / 1_000,
        },
    }


class FoodIndexBuilderTests(unittest.TestCase):
    def test_builder_collapses_search_families_but_keeps_barcode_skus(self) -> None:
        values = [
            record("3011360021502", "Fol Epi Classic", 361, 500, modified=2),
            record("3123930651696", "Fol Epi, Classic", 362, 510, modified=3),
            record("7613035974685", "Fol Epi Classic 150 g", 360, 520, modified=4),
            record("4056489626633", "Classic", 361, 500, modified=1),
            record("4002468181006", "Fol Epi Light", 280, 600),
            record("0098001463511", "US only", 100, 10,
                   countries=["en:united-states"]),
            {"code": "12345678", "product_name": "Bad checksum",
             "countries_tags": ["en:germany"],
             "nutriments": {"energy-kcal_100g": 100}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "off.jsonl"
            source.write_text("".join(json.dumps(value) + "\n" for value in values),
                              encoding="utf-8")
            output = temporary / "dist"
            subprocess.run([
                "python3", str(ROOT / "build_index.py"),
                "--off-jsonl", str(source),
                "--market", "DE=en:germany",
                "--market", "US=en:united-states",
                "--output-dir", str(output),
                "--catalog-version", "2026-09-01T00:00:00Z",
            ], check=True)

            database = sqlite3.connect(output / "akari-food-de.sqlite")
            self.assertEqual(database.execute("SELECT COUNT(*) FROM family").fetchone()[0], 2)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM sku").fetchone()[0], 5)
            family = database.execute(
                "SELECT canonical_name, variant_count FROM family WHERE normalized_name = 'classic'"
            ).fetchone()
            self.assertEqual(family, ("Fol Epi Classic 150 g", 4))
            results = database.execute(
                """SELECT f.canonical_name FROM family_search s
                   JOIN family f ON f.id = s.rowid
                   WHERE family_search MATCH 'fol* AND epi*'""").fetchall()
            self.assertEqual({row[0] for row in results},
                             {"Fol Epi Classic 150 g", "Fol Epi Light"})
            database.close()

            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["schemaVersion"], 1)
            self.assertEqual(manifest["markets"]["DE"]["familyCount"], 2)
            self.assertEqual(manifest["markets"]["US"]["skuCount"], 1)

    def test_builder_reads_the_official_tab_separated_csv_shape(self) -> None:
        value = {
            "code": "3011360021502",
            "product_name": "Fol Epi Classic",
            "brands": "Fol Epi",
            "countries_tags": "en:france,en:germany",
            "last_modified_t": "1788256800",
            "completeness": "0.9",
            "serving_size": "1 slice (40 g)",
            "serving_quantity": "40",
            "image_url": "https://example.com/fol-epi.jpg",
            "nutriscore_grade": "d",
            "nova_group": "4",
            "nutrient_levels_tags": (
                "en:fat-in-high-quantity,en:sugars-in-low-quantity"
            ),
            "energy-kcal_100g": "361",
            "proteins_100g": "24",
            "fat_100g": "29",
            "carbohydrates_100g": "0.5",
            "calcium_100g": "0.5",
            "selenium_100g": "0.000012",
            "unused_large_field": "x" * 140_000,
        }
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "off.csv.gz"
            with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=list(value), delimiter="\t")
                writer.writeheader()
                writer.writerow(value)
            output = temporary / "dist"
            subprocess.run([
                "python3", str(ROOT / "build_index.py"),
                "--off-export", str(source),
                "--market", "DE=en:germany",
                "--output-dir", str(output),
                "--catalog-version", "2026-09-01T00:00:00Z",
            ], check=True)

            database = sqlite3.connect(output / "akari-food-de.sqlite")
            product = database.execute(
                """SELECT calories, nutrient_count, micronutrient_count,
                          nutrient_levels_json
                   FROM sku""").fetchone()
            database.close()
            self.assertEqual(product[:3], (361, 6, 2))
            self.assertEqual(json.loads(product[3]), {"fat": "high", "sugars": "low"})


if __name__ == "__main__":
    unittest.main()
