# AkariFoodIndex

This pipeline publishes two deliberately separate kinds of SQLite food data:

- market-specific Open Food Facts product and barcode indexes; and
- Akari's generic-food reference index built from BLS, USDA FoodData Central,
  UK CoFID, French Ciqual, and Japan MEXT composition tables.

Keeping the ODbL product layer separate from the national reference tables
preserves source provenance and keeps each database's licence unambiguous.

Source exports come from the official [Open Food Facts data page](https://world.openfoodfacts.org/data).
Database and pipeline licensing are documented in `LICENSE.md`.

The index has two product levels:

- `family`: the single canonical result visible in text search.
- `sku`: each retained barcode/package variant, used for exact barcode scans.

Records with the same normalized brand and product name join one family. The
most complete, current, structurally valid SKU represents that family in
search; every barcode remains queryable and every imported record retains its
source hash and validation history. Package sizes such as `150 g` are removed
only from the family identity, so differently sized packs do not become
duplicate search results.

Akari downloads only the selected market database into Application Support and
keeps at most one market database at a time. Full products the person opens or
scans are retained in a capped 250-item hot cache. Neither generated catalogue
nor hot cache is part of the App Store bundle or iCloud backup.

## Build

Download the official Open Food Facts tab-separated CSV export and run:

```sh
python3 FoodIndex/build_index.py \
  --off-export en.openfoodfacts.org.products.csv.gz \
  --market DE=en:germany \
  --market AT=en:austria \
  --market CH=en:switzerland \
  --market US=en:united-states \
  --output-dir FoodIndex/dist
```

`dist/manifest.json` contains version, hash, size, count, licence and download
metadata for each database. Generated databases and source dumps never belong
in Git history; publish them as GitHub Release assets or object-storage files.

The release also contains `reference-foods.sqlite` and
`reference-manifest.json`. The reference database is built and reviewed in the
Akari application repository, then its hash, schema, source counts, integrity,
and 103-item curated verification boundary are checked again here before it is
published. National-table rows do not become verified merely because they have
many nutrients.

## Verify

```sh
python3 -m unittest FoodIndex/test_index.py
```

Open Food Facts data is licensed under ODbL 1.0. Reference-table terms range
from CC0 to attribution licences and are listed in `LICENSE.md`. Product images
have separate CC BY-SA terms. Keep attribution visible and review the upstream
reuse guidance before changing distribution or contribution behavior.

## Publishing

`.github/workflows/refresh.yml` is the complete distribution workflow. It
refreshes the core German-speaking and English-speaking markets weekly,
validates the independent generic-food reference database, verifies every
SQLite file and SHA-256 digest, then publishes immutable GitHub Release assets
with a stable `latest` URL.

Published catalogues are available from the
[`hejrafa/AkariFoodIndex`](https://github.com/hejrafa/AkariFoodIndex) releases.
