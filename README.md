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
representative first needs valid calories and macros, then good serving data,
the market's language, and freshness; micronutrient breadth is only a late
tie-breaker. Every barcode remains queryable and every imported record retains
its source hash and validation history. Package sizes such as `150 g` are
removed only from the family identity, so differently sized packs do not
become duplicate search results.

Each family's FTS row accumulates all localized and generic names, localized
categories, category tags, package-free forms, and narrow compound aliases
from every SKU. The displayed name still comes from the representative SKU,
but a useful alias on another package variant remains searchable.

Schema v4 keeps the label's nutritional basis (`100 g` or `100 ml`), the
source-provided serving amount, unit, and label, and the complete sparse set of
Akari-supported nutrients. It also retains localized and generic names,
categories, an explicit alcohol classification, and an evidence-backed artwork classification. Mass and volume stay
separate: the index does not infer density or convert milliliters to grams.

Akari downloads only the selected market database into Application Support and
keeps at most one market database at a time. Full products the person opens or
scans are retained in a capped 250-item hot cache. Neither generated catalogue
nor hot cache is part of the App Store bundle or iCloud backup.

## Build

Commands below use the app checkout’s `FoodIndex/` prefix. In the standalone
AkariFoodIndex repository, omit that prefix.

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

## Food classification and artwork

`artwork-classification.json` is the owned presentation taxonomy. Copy it verbatim
to `Akari/FoodArtworkClassification.json` when changing rules; shared regression
fixtures and CI check that both implementations stay aligned. Source category
IDs are matched exactly. Manufacturer-reviewed product-line rules include URLs,
review dates, and narrow name qualifiers. Nutrient and alcohol logic is separate.

`classify_artwork.py` writes each SKU's category, artwork ID, evidence, source, and
rule version. `audit_classification.py` produces coverage counts and a review
queue including unknown identities and known types with no suitable artwork.
See `analysis/README.md` for the initial nine-market audit and its limitations.

Releases expose `manifest-v4.json` and `*-v4.sqlite` for classified catalogues.
`prepare_release.py` preserves the legacy `manifest.json` with immutable URLs to
the previous compatible catalogues, so older app versions keep working. The
app falls back to legacy only if the new manifest has not been published (404).
Do not delete the pinned legacy release while supporting those clients.

Run all builder, classification, and compatibility checks:

```sh
python3 -m unittest discover -s FoodIndex -p 'test_*.py'
```
