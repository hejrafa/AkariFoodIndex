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
            # Macros that carry the given energy at 4/9/4 kcal per gram, so the
            # plausibility rule (b220) keeps every fixture row.
            "proteins_100g": round(calories * 0.3 / 4, 3),
            "fat_100g": round(calories * 0.6 / 9, 3),
            "carbohydrates_100g": round(calories * 0.1 / 4, 3),
            "calcium_100g": calcium / 1_000,
        },
    }


def build(values: list[dict], output: Path, *markets: str) -> dict:
    """Run the builder on the records for the markets and return the manifest."""
    source = output.parent / f"{output.name}-off.jsonl"
    source.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")
    command = ["python3", str(ROOT / "build_index.py"), "--off-jsonl", str(source),
               "--output-dir", str(output), "--catalog-version", "2026-10-30T00:00:00Z"]
    for market in markets or ("DE=en:germany",):
        command += ["--market", market]
    subprocess.run(command, check=True, capture_output=True)
    return json.loads((output / "manifest.json").read_text(encoding="utf-8"))


def sku_names(output: Path, market: str = "de") -> set[str]:
    database = sqlite3.connect(output / f"akari-food-{market}.sqlite")
    try:
        return {row[0] for row in database.execute("SELECT product_name FROM sku")}
    finally:
        database.close()


class FoodIndexBuilderTests(unittest.TestCase):
    def test_menu_claims_file_is_current(self) -> None:
        """The worker fetches chains/menu-claims.json from the mirror, so the
        committed file must be what the builder derives from the chain files,
        staples and recipes today; regenerate it with --menu-claims."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_index", ROOT / "build_index.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.menu_claims(),
                         json.loads((ROOT / "chains" / "menu-claims.json").read_text(encoding="utf-8")))
        self.assertIn({"name": "big mac", "chainKey": "mcdonalds-de", "chain": "McDonald's Deutschland",
                       "per100g": {"calories": 235.0, "fat": 12.0, "carbs": 18.0, "protein": 12.0}},
                      module.menu_claims()["claims"])

    def test_pack_rules_reject_implausible_unscanned_and_borrowed_menu_items(self) -> None:
        """b220: a market pack keeps out nutrition that cannot be (energy far
        from its macros, a nutrient above 100 g), unbranded unscanned stubs, and
        another company's menu item under a brand that is not the chain, while
        alcohol, polyols, scanned products and the chain's own items stay."""
        beer = record("4000000000013", "Pils", 43, 5, brand="Rothaus")
        beer["nutriments"].update({"proteins_100g": 0.5, "fat_100g": 0, "carbohydrates_100g": 3.5,
                                   "alcohol_100g": 5.1})
        gum = record("4000000000020", "Kaugummi zuckerfrei", 160, 5, brand="Wrigley")
        gum["nutriments"].update({"proteins_100g": 0, "fat_100g": 0.5, "carbohydrates_100g": 65,
                                  "polyols_100g": 64})
        impossible_energy = record("4000000000037", "Nussriegel", 55, 5, brand="Riegelwerk")
        impossible_energy["nutriments"].update({"fat_100g": 29, "proteins_100g": 24})
        impossible_mass = record("4000000000044", "Fruchtgummi", 340, 5, brand="Gummiwerk")
        impossible_mass["nutriments"]["carbohydrates_100g"] = 180
        stub = record("4000000000051", "Riegel", 400, 5, brand="")
        stub["completeness"] = 0.3
        scanned_stub = record("4000000000068", "Müsliriegel", 400, 5, brand="")
        scanned_stub.update({"completeness": 0.3, "unique_scans_n": 4})
        # McDonald's publishes the Big Mac at 235 kcal, 12 g fat, 18 g carbs, 12 g protein per 100 g.
        big_mac = {"energy-kcal_100g": 235, "fat_100g": 12, "carbohydrates_100g": 18, "proteins_100g": 12}
        borrowed = record("4000000000075", "Big Mac", 235, 5, brand="Ikea")
        borrowed["nutriments"].update(big_mac)
        own = record("4000000000082", "Big Mac", 235, 5, brand="McDonald's")
        own["nutriments"].update(big_mac)
        namesake = record("4000000000112", "Big Mac", 250, 5, brand="Tiefkühlhaus")
        scanned_borrowed = record("4000000000099", "Whopper", 250, 5, brand="Tiefkühlhaus")
        scanned_borrowed["popularity_tags"] = ["top-5000-de-scans-2025"]
        makers_own = record("4000000000105", "Coca-Cola 0,25 l", 42, 5, brand="Coca-Cola")
        wine = record("4000000000129", "Grüner Veltliner", 73, 5, brand="Weingut")
        wine["nutriments"].update({"proteins_100g": 0.1, "fat_100g": 0, "carbohydrates_100g": 1.5, "energy-kcal_100ml": 73})
        wine["nutrition_data_per"] = "100ml"
        values = [beer, gum, impossible_energy, impossible_mass, stub, scanned_stub,
                  borrowed, own, namesake, scanned_borrowed, makers_own, wine]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            manifest = build(values, output)
            kept = {row[0]: row[1] for row in sqlite3.connect(output / "akari-food-de.sqlite")
                    .execute("SELECT barcode, product_name FROM sku")}
            self.assertEqual(kept, {"4000000000013": "Pils", "4000000000020": "Kaugummi zuckerfrei",
                                    "4000000000068": "Müsliriegel", "4000000000082": "Big Mac",
                                    "4000000000112": "Big Mac", "4000000000099": "Whopper",
                                    "4000000000105": "Coca-Cola 0,25 l", "4000000000129": "Grüner Veltliner"})
            self.assertEqual(manifest["markets"]["DE"]["rejected"],
                             {"implausible-nutrition": 2, "unscanned-unbranded": 1,
                              "chain-item-under-another-brand": 1})
            sidecar = output / manifest["markets"]["DE"]["rejectedFilename"]
            rejected = {json.loads(line)["code"]: json.loads(line)["rule"]
                        for line in sidecar.read_text(encoding="utf-8").splitlines()}
            self.assertEqual(rejected, {"4000000000037": "implausible-nutrition",
                                        "4000000000044": "implausible-nutrition",
                                        "4000000000051": "unscanned-unbranded",
                                        "4000000000075": "chain-item-under-another-brand"})
            self.assertEqual(json.loads((output / "rejections.json").read_text())["markets"]["DE"],
                             manifest["markets"]["DE"]["rejected"])

    def test_builder_drops_test_entries_but_keeps_real_test_brand_and_words(self) -> None:
        values = [
            record("3011360021502", "Test nutriscan", 55, 10, brand=""),
            record("3123930651696", "Testing", 55, 10, brand=""),
            record("7613035974685", "Test", 55, 10, brand="Real Brand"),
            record("4056489626633", "Testaroli", 55, 10, brand=""),
            record("5901234123457", "Chocolate bar", 55, 10, brand="Test"),
            record("4006381333931", "Fromage cottage", 55, 10, brand="Seal test"),
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
                "--output-dir", str(output),
                "--catalog-version", "2026-09-13T00:00:00Z",
            ], check=True)

            database = sqlite3.connect(output / "akari-food-de.sqlite")
            names = {row[0] for row in database.execute("SELECT product_name FROM sku")}
            database.close()
            self.assertEqual(names, {"Chocolate bar", "Testaroli"})

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
            rule_version = json.loads((ROOT / "artwork-classification.json").read_text())["version"]
            self.assertTrue(all(value["version"] == rule_version for value in classifications))
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
                "--off-export", str(source), "--allow-legacy-csv-for-audit",
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

    def test_builder_streams_a_compressed_jsonl_export_from_stdin(self) -> None:
        value = record("3011360021502", "Streamed Food", 361, 500)
        compressed = gzip.compress((json.dumps(value) + "\n").encode())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            subprocess.run([
                "python3", str(ROOT / "build_index.py"),
                "--off-export", "-", "--off-export-gzip",
                "--market", "DE=en:germany",
                "--output-dir", str(output),
                "--catalog-version", "2026-09-13T00:00:00Z",
            ], input=compressed, check=True)

            database = sqlite3.connect(output / "akari-food-de.sqlite")
            self.assertEqual(database.execute(
                "SELECT product_name FROM sku").fetchone(), ("Streamed Food",))
            database.close()

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

    def test_builder_corrects_explicit_drink_with_conflicting_mass_basis(self) -> None:
        value = {
            "code": "4043533000211",
            "product_name": "Rhabarbergetränk",
            "brands": "Oppacher",
            "countries_tags": ["en:germany"],
            "nutrition_data_per": "100g",
            "serving_size": "500 ml",
            "serving_quantity": 500,
            "serving_quantity_unit": "ml",
            "nutriments": {
                "energy-kcal_100g": 28,
                "carbohydrates_100g": 6.2,
                "sugars_100g": 6.1,
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
                "--catalog-version", "2026-09-10T00:00:00Z",
            ], check=True)

            database = sqlite3.connect(output / "akari-food-de.sqlite")
            product = database.execute(
                "SELECT nutrition_basis, serving_unit, serving_milliliters, calories FROM sku"
            ).fetchone()
            database.close()
            self.assertEqual(product, ("per100Milliliters", "ml", 500, 28))

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
