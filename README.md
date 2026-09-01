# AkariFoodIndex

This pipeline turns the Open Food Facts bulk export into small, market-specific
SQLite search indexes for Akari. It keeps the original ODbL-derived packaged
product layer separate from Akari's bundled BLS/USDA reference-food overlay.

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

Download the official Open Food Facts JSONL export and run:

```sh
python3 FoodIndex/build_index.py \
  --off-jsonl openfoodfacts-products.jsonl.gz \
  --market DE=en:germany \
  --market AT=en:austria \
  --market CH=en:switzerland \
  --market US=en:united-states \
  --output-dir FoodIndex/dist
```

`dist/manifest.json` contains version, hash, size, count, licence and download
metadata for each database. Generated databases and source dumps never belong
in Git history; publish them as GitHub Release assets or object-storage files.

## Verify

```sh
python3 -m unittest FoodIndex/test_index.py
```

Open Food Facts data is licensed under ODbL 1.0. Product images have separate
CC BY-SA terms. Keep attribution visible and review the upstream reuse guidance
before changing distribution or contribution behavior.

## Publishing

`.github/workflows/refresh.yml` is the complete distribution workflow. It
refreshes the core German-speaking and English-speaking markets weekly,
verifies every database and SHA-256 digest, then publishes immutable GitHub
Release assets with a stable `latest` URL.

Published catalogues are available from the
[`hejrafa/AkariFoodIndex`](https://github.com/hejrafa/AkariFoodIndex) releases.
