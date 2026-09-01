#!/usr/bin/env python3
from __future__ import annotations

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
            self.assertEqual(database.execute("SELECT COUNT(*) FROM sku").fetchone()[0], 4)
            family = database.execute(
                "SELECT canonical_name, variant_count FROM family WHERE normalized_name LIKE 'fol epi classic'"
            ).fetchone()
            self.assertEqual(family, ("Fol Epi Classic 150 g", 3))
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


if __name__ == "__main__":
    unittest.main()
