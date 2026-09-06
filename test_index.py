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
        values[0]["product_name_fr"] = "Fol Epi Tradition française"
        values[0]["generic_name_de"] = "Halbhart Käse"
        values[0]["categories_de"] = "Käse Snacks"
        values[1]["categories_tags"] = ["en:semi-hard-cheeses"]
        values[2]["product_name_de"] = "Fol Epi klassischer Käse"
        values[2]["generic_name_de"] = "Schnittkäse"
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
                "SELECT canonical_name, variant_count FROM family "
                "WHERE family_key = 'fol epi|classic'"
            ).fetchone()
            self.assertEqual(family, ("Fol Epi klassischer Käse", 4))
            results = database.execute(
                """SELECT f.canonical_name FROM family_search s
                   JOIN family f ON f.id = s.rowid
                   WHERE family_search MATCH 'fol* AND epi*'""").fetchall()
            self.assertEqual({row[0] for row in results},
                             {"Fol Epi klassischer Käse", "Fol Epi Light"})
            for query in (
                    "schnittkase*",             # representative generic name
                    "tradition* AND francaise*",  # non-representative localized name
                    "halbhartkase*",            # generated compound alias
                    "kasesnacks*",              # localized category alias
                    "semihardcheeses*",         # normalized category tag alias
            ):
                with self.subTest(query=query):
                    aliases = database.execute(
                        """SELECT f.canonical_name FROM family_search s
                           JOIN family f ON f.id = s.rowid
                           WHERE family_search MATCH ?""", (query,)).fetchall()
                    self.assertEqual(aliases, [("Fol Epi klassischer Käse",)])
            classifications = [json.loads(r[0]) for r in database.execute(
                "SELECT artwork_classification_json FROM sku")]
            self.assertTrue(all(value["categoryID"] == "cheese" for value in classifications))
            self.assertTrue(all(value["version"] == 1 for value in classifications))
            database.close()

            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["schemaVersion"], 4)
            self.assertEqual(manifest["markets"]["DE"]["familyCount"], 2)
            self.assertEqual(manifest["markets"]["US"]["skuCount"], 1)

    def test_builder_uses_market_localized_names_and_keeps_all_names_searchable(self) -> None:
        value = record(
            "3011360021502", "Nom principal", 361, 500,
            countries=["en:germany", "en:united-states"])
        value.update({
            "lang": "fr",
            "product_name_de": "Deutscher Name",
            "product_name_en": "English Name",
            "generic_name": "Fromage",
            "generic_name_de": "Deutscher Käse",
            "generic_name_en": "English cheese",
        })
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "off.jsonl"
            source.write_text(json.dumps(value) + "\n", encoding="utf-8")
            output = temporary / "dist"
            subprocess.run([
                "python3", str(ROOT / "build_index.py"),
                "--off-jsonl", str(source),
                "--market", "DE=en:germany",
                "--market", "US=en:united-states",
                "--output-dir", str(output),
                "--catalog-version", "2026-09-03T00:00:00Z",
            ], check=True)

            german = sqlite3.connect(output / "akari-food-de.sqlite")
            us = sqlite3.connect(output / "akari-food-us.sqlite")
            self.assertEqual(german.execute(
                "SELECT product_name, generic_name FROM sku").fetchone(),
                ("Deutscher Name", "Deutscher Käse"))
            self.assertEqual(us.execute(
                "SELECT product_name, generic_name FROM sku").fetchone(),
                ("English Name", "English cheese"))
            for database in (german, us):
                self.assertEqual(database.execute(
                    """SELECT COUNT(*) FROM family_search
                       WHERE family_search MATCH 'nom* AND principal*'""").fetchone()[0], 1)
                self.assertEqual(database.execute(
                    """SELECT COUNT(*) FROM family_search
                       WHERE family_search MATCH 'deutscher*'""").fetchone()[0], 1)
                self.assertEqual(database.execute(
                    """SELECT COUNT(*) FROM family_search
                       WHERE family_search MATCH 'english*'""").fetchone()[0], 1)
            german.close()
            us.close()

    def test_representative_prefers_usable_market_record_before_micronutrients(self) -> None:
        invalid_macros = record(
            "3011360021502", "Priority Food", 300, 500, modified=1_000)
        invalid_macros["nutriments"]["proteins_100g"] = 150
        no_serving = record(
            "3123930651696", "Priority Food", 300, 500, modified=1_000)
        no_serving["product_name_de"] = "Prioritätsessen"
        no_locale = record(
            "7613035974685", "Priority Food", 300, 500, modified=1_000)
        older_with_micro = record(
            "4056489626633", "Priority Food", 300, 500, modified=10)
        winner = record(
            "4002468181006", "Priority Food", 300, 500, modified=20)

        for value in (invalid_macros, no_locale, older_with_micro, winner):
            value.update({
                "serving_quantity": 40,
                "serving_quantity_unit": "g",
                "serving_size": "1 slice (40 g)",
            })
        for value in (invalid_macros, older_with_micro, winner):
            value["product_name_de"] = "Prioritätsessen"
        # The older candidate has much richer micronutrient coverage. Freshness
        # must still decide between otherwise equally usable localized records.
        older_with_micro["nutriments"].update({
            "magnesium_100g": 0.03,
            "potassium_100g": 0.2,
            "iron_100g": 0.002,
            "zinc_100g": 0.003,
            "selenium_100g": 0.00001,
            "vitamin-c_100g": 0.01,
        })
        winner["nutriments"].pop("calcium_100g")

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "off.jsonl"
            source.write_text(
                "".join(json.dumps(value) + "\n" for value in (
                    invalid_macros, no_serving, no_locale, older_with_micro, winner,
                )), encoding="utf-8")
            output = temporary / "dist"
            subprocess.run([
                "python3", str(ROOT / "build_index.py"),
                "--off-jsonl", str(source),
                "--market", "DE=en:germany",
                "--output-dir", str(output),
                "--catalog-version", "2026-09-03T00:00:00Z",
            ], check=True)

            database = sqlite3.connect(output / "akari-food-de.sqlite")
            representative = database.execute(
                """SELECT s.barcode, f.canonical_name
                   FROM family f
                   JOIN sku s ON s.id = f.representative_sku_id""").fetchone()
            database.close()
            self.assertEqual(representative,
                             ("4002468181006", "Prioritätsessen"))

    def test_builder_reads_the_official_tab_separated_csv_shape(self) -> None:
        value = {
            "code": "3011360021502",
            "product_name": "Fol Epi Classic",
            "product_name_de": "Fol Epi Klassik",
            "product_name_fr": "Fol Epi Classique",
            "generic_name": "Semi-hard cheese",
            "generic_name_de": "Schnittkäse",
            "brands": "Fol Epi",
            "categories": "Dairy products,Cheeses",
            "categories_tags": "en:dairies,en:cheeses",
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
                          nutrient_levels_json, nutrients_json,
                          localized_names_json, generic_name,
                          localized_generic_names_json, categories_json,
                          category_tags_json, alcohol_classification
                   FROM sku""").fetchone()
            database.close()
            self.assertEqual(product[:3], (361, 6, 2))
            self.assertEqual(json.loads(product[3]), {"fat": "high", "sugars": "low"})
            self.assertEqual(json.loads(product[4]), {
                "calories": 361, "protein": 24, "fat": 29, "carbs": 0.5,
                "calcium": 500, "selenium": 12,
            })
            self.assertEqual(json.loads(product[5]), {
                "de": "Fol Epi Klassik", "fr": "Fol Epi Classique",
            })
            self.assertEqual(product[6], "Schnittkäse")
            self.assertEqual(json.loads(product[7]), {"de": "Schnittkäse"})
            self.assertEqual(json.loads(product[8]), ["Dairy products", "Cheeses"])
            self.assertEqual(json.loads(product[9]), ["en:dairies", "en:cheeses"])
            self.assertEqual(product[10], "unknown")

    def test_builder_preserves_volume_basis_and_named_serving(self) -> None:
        value = {
            "code": "3017620422003",
            "product_name": "Sparkling drink",
            "brands": "Example",
            "countries_tags": ["en:germany"],
            "nutrition_data_per": "100ml",
            "product_quantity_unit": "ml",
            "serving_size": "1 bottle (330 ml)",
            "serving_quantity": 330,
            "serving_quantity_unit": "ml",
            "nutriments": {
                "energy-kcal_100ml": 42,
                "carbohydrates_100ml": 10,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "off.jsonl"
            source.write_text(json.dumps(value) + "\n", encoding="utf-8")
            output = temporary / "dist"
            subprocess.run([
                "python3", str(ROOT / "build_index.py"),
                "--off-jsonl", str(source),
                "--market", "DE=en:germany",
                "--output-dir", str(output),
                "--catalog-version", "2026-09-03T00:00:00Z",
            ], check=True)

            database = sqlite3.connect(output / "akari-food-de.sqlite")
            product = database.execute(
                """SELECT nutrition_basis, serving_amount, serving_unit,
                          serving_grams, serving_milliliters, serving_label, calories
                   FROM sku""").fetchone()
            database.close()
            self.assertEqual(product, (
                "per100Milliliters", 330, "ml", None, 330,
                "1 bottle (330 ml)", 42,
            ))

    def test_builder_persists_authoritative_alcohol_classification(self) -> None:
        cocktail = record("3017620422003", "Sex on the Beach", 120, 0,
                          brand="Example")
        cocktail["categories_tags"] = ["en:alcoholic-beverages", "en:cocktails"]
        alcohol_free = record("5449000000996", "Alkoholfreies Bier", 25, 0,
                              brand="Example")
        # The explicit claim must veto the broader upstream beer category.
        alcohol_free["categories_tags"] = ["en:beverages", "en:beers"]
        fruit_tea = record(
            "0098001463511", "Sex on the Beach Kaltaufguss-Früchtetee", 2, 0,
            brand="Example")
        fruit_tea["categories_tags"] = ["en:teas", "en:fruit-teas"]
        cocktail_sauce = record("4000417025005", "Cocktail sauce", 128, 0,
                                brand="Example")
        cocktail_sauce["categories_tags"] = ["en:sauces", "en:cocktail-sauces"]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "off.jsonl"
            source.write_text(
                "".join(json.dumps(value) + "\n"
                        for value in (cocktail, alcohol_free, fruit_tea,
                                      cocktail_sauce)),
                encoding="utf-8")
            output = temporary / "dist"
            subprocess.run([
                "python3", str(ROOT / "build_index.py"),
                "--off-jsonl", str(source),
                "--market", "DE=en:germany",
                "--output-dir", str(output),
                "--catalog-version", "2026-09-03T00:00:00Z",
            ], check=True)

            database = sqlite3.connect(output / "akari-food-de.sqlite")
            classifications = dict(database.execute(
                "SELECT product_name, alcohol_classification FROM sku"))
            database.close()
            self.assertEqual(classifications, {
                "Sex on the Beach": "alcoholic",
                "Alkoholfreies Bier": "nonAlcoholic",
                "Sex on the Beach Kaltaufguss-Früchtetee": "unknown",
                "Cocktail sauce": "unknown",
            })


if __name__ == "__main__":
    unittest.main()
