# Akari Food Index

The pipeline that builds Akari's market-specific Open Food Facts product and
barcode indexes and publishes them every week. Open Food Facts data is
licensed under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/),
a share-alike licence, so this pipeline and the catalogues it derives are
public. Source exports come from the official
[Open Food Facts data page](https://world.openfoodfacts.org/data). Database and
pipeline licensing are documented in `LICENSE.md`.

Akari's reviewed food data (its generic-food reference index built from the
BLS, USDA FoodData Central, CoFID, Ciqual and MEXT composition tables, its
verified names, portions, recipes, chain menus and label readings) is built
and reviewed in the Akari app repository and is not part of this one. The app
reads it from `https://foods.joinakari.com`, where the app repository's
Sunday data pack workflow publishes it; the two files this pipeline needs of
it are fetched from there before every build (see Publishing).

## What the index holds

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
categories, an explicit alcohol classification, and an evidence-backed artwork
classification. Mass and volume stay separate: the index does not infer
density or convert milliliters to grams.

Akari downloads only the selected market database into Application Support and
keeps at most one market database at a time. Full products the person opens or
scans are retained in a capped 250-item hot cache. Neither generated catalogue
nor hot cache is part of the App Store bundle or iCloud backup.

## Build

Stream the official compressed Open Food Facts JSONL export directly into the
builder so the multi-gigabyte source does not consume local disk space:

```sh
curl --fail --location \
  https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz | \
python3 build_index.py --off-export - --off-export-gzip \
  --market DE=en:germany \
  --market AT=en:austria \
  --market CH=en:switzerland \
  --market US=en:united-states \
  --output-dir dist
```

`dist/manifest.json` contains version, hash, size, count, licence and download
metadata for each database. Generated databases and source dumps never belong
in Git history; publish them as release assets or object-storage files.

Before a build, fetch rule 4's finished claim list (below) to
`chains/menu-claims.json`:

```sh
mkdir -p chains
curl --fail --location --output chains/menu-claims.json \
  https://foods.joinakari.com/latest/menu-claims.json
```

### What a market pack leaves out

Open Food Facts is edited by anyone, so a market pack applies four rules
before a product enters it (`build_index.py`, 30 October 2026). Every barcode
a rule removes is written, with the rule and a one-line reason, to the
market's sidecar `rejected-<market>.jsonl` next to the database; the release
carries the sidecars, `rejections.json` sums them per market and rule, and each
market's manifest entry repeats its counts under `rejected`, which
`verify_release.py` checks against the sidecar. A product that is missing from
Akari's barcode scan can therefore always be looked up there.

1. **Implausible nutrition.** No nutrient may exceed 100 g per 100 g or ml, and
   the declared energy must agree with the energy its components carry, at
   4 kcal per g of protein and carbohydrate, 9 of fat, 2 of fibre, 7 of
   alcohol (declared as % vol or g), 2.4 of polyols and 3 of organic acids,
   within 20 % or 12 kcal. A product whose energy cannot be computed (a macro
   missing, or an alcoholic drink that declares no alcohol) is not judged.
2. **Market.** A product enters a market's pack only when its Open Food Facts
   record lists that country. (The app's live Open Food Facts search is a
   separate door and is not filtered here.)
3. **Popularity floor.** A product with no brand, no scans and a record less
   than half complete is a stub nobody has confirmed and stays out.
4. **Another company's menu item.** A product whose name is, or begins with,
   a menu item of one of the chains Akari lists and whose values per 100 g are
   the chain's published ones (calories within 10 % or 10 kcal, fat, carbs and
   protein each within 15 % or 1.5 g; items under 50 kcal per 100 g never
   count, since a drink's few kilocalories match anything) stays out when its
   brand is not that chain, the name is not the brand's own product that the
   chain merely sells (a Coca-Cola on a Burger King menu), and nobody has
   scanned it in the market. Menu names made only of generic food words
   ("Cheeseburger", "Blueberry muffin", "Caffè latte") never claim another
   maker's product. A product that merely shares a menu item's name keeps its
   own label and stays.

The rule constants sit together at the top of `build_index.py`
(`ENERGY_TOLERANCE_SHARE` … `CHAIN_MATCH_MACRO_GRAMS`). Rule 4's names and
values are the finished claim list `chains/menu-claims.json`, which the Akari
app repository derives from its chain menus and publishes at
`https://foods.joinakari.com/latest/menu-claims.json`; the builder reads it
(`claimed_menu_names()`) because this repository carries no chain file, and
the live-search worker applies the same four rules from the same list to the
products the app's online search returns.

## Verify

```sh
python3 -m unittest discover -p 'test_*.py'
```

`test_index.py` builds small catalogues through the builder and checks the
four rules, the family and SKU shape, the localized names, the serving basis
and the alcohol classification; its rule 4 case needs `chains/menu-claims.json`
fetched as above. `test_classification.py`, `test_food_quality.py`,
`test_release.py` and `test_serving_validation.py` cover the artwork rules, the
category taxonomy, the release manifests and the serving identities.

## Publishing

`.github/workflows/refresh.yml` is the complete distribution workflow, run on
Sundays at 09:17 UTC and on demand. It first fetches from
`https://foods.joinakari.com/latest/` the two files it needs of Akari's
reviewed data, published there by the app repository's data pack workflow
three hours earlier: the data pack's zip, whose `ReferenceFoods.sqlite` is the
national reference index (checked against the pack manifest's SHA-256), and
`menu-claims.json`. It then refreshes the core German-speaking and
English-speaking markets, validates the reference database, verifies every
SQLite file and SHA-256 digest, and publishes the same files twice: to
Cloudflare R2 first, then as release assets of this repository. Each copy's
manifests point at its own host, and the run ends with a probe of the
manifest the app reads.

- `https://foods.joinakari.com/latest/` is what the app reads:
  `manifest-v4.json`, `manifest.json` and the files they name, replaced every
  week. It is the R2 bucket `akari-food-index` (EU jurisdiction); the manifests
  are uploaded after their files.
- `https://foods.joinakari.com/releases/<tag>/` holds an immutable snapshot of
  each release. The newest three are kept; older ones are deleted at the end of
  the run.
- This repository's releases carry the same files.

The release also contains `reference-foods.sqlite` and
`reference-manifest.json`. The reference database is built and reviewed in the
Akari app repository; its hash, schema, source counts, integrity and curated
verification coverage for every national source are checked again here before
it is published. National-table rows do not become verified merely because
they have many nutrients.

Releases expose `manifest-v4.json` and `*-v4.sqlite` for classified catalogues.
`prepare_release.py` preserves the legacy `manifest.json` (schema 1) with
immutable URLs to the previous compatible catalogues, so older app versions
keep working; the workflow reads that manifest from R2 and keeps the release
it pins. The app falls back to legacy only if the new manifest has not been
published (404). Do not delete the pinned legacy release while supporting
those clients.

The R2 steps need the repository secrets `CLOUDFLARE_API_TOKEN` (with Account >
Workers R2 Storage > Edit) and `CLOUDFLARE_ACCOUNT_ID`. Without them the run
stops before either copy changes. The upload refuses a `dist/` larger than 3 GB.

## Food classification and artwork

`artwork-classification.json` is the owned presentation taxonomy; the Akari
app carries the same rules and shared fixtures (`classification-fixtures.json`)
keep both implementations aligned. Source category IDs are matched exactly.
Manufacturer-reviewed product-line rules include URLs, review dates, and narrow
name qualifiers. Nutrient and alcohol logic is separate.

Rules can declare `ingredientCategories`: when both occur in a food name, the
finished form owns its ingredient or flavor (for example peanut butter cookies,
chocolate milk, or protein bars). The same relationship resolves broad category
and alternate-name hints. Exact food terms before commas retain catalog wording
such as “Chocolate, milk” when there is a known ingredient relationship; powder
and other preparation identities are still considered. Shared fixtures cover
both directions and ambiguous German terms such as Eiweiß.

`classify_artwork.py` writes each SKU's category, artwork ID, evidence, source,
and rule version. `audit_classification.py` produces coverage counts and a
review queue including unknown identities and known types with no suitable
artwork. `analysis/branded-sample-2026-09-06.json` is the one sample a test
classifies, so a rule change that moves a branded product's artwork fails a
test.

## Reported nutrition, source research and release gates

Production builds require the full official JSONL export. The flat CSV cannot
preserve reported-versus-estimated provenance: the September 2026 source audit
found recipe-estimated vitamins in its ordinary nutrient columns. It is accepted
only with `--allow-legacy-csv-for-audit`, and that provenance cannot pass
`verify_release.py`.

`normalize_off_nutrition.py` reads the current OFF `nutrition.input_sets` model:
only packaging/manufacturer sets, only as-sold nutrition, explicit units and
source quantities. It preserves label values over computed values, converts
reported mass/volume servings independently, rejects unknown units and percent
daily values, and never imports the aggregated set or `nutriments_estimated`.
Legacy JSON's separate `nutriments` object remains supported.

`build_food_taxonomy.py` compiles the official category graph, multilingual
identities, and direct Ciqual links whose French names agree with the current
ANSES table, against the reference index the refresh fetched. Proxy links and
unspecified averages are excluded. The app still requires compatible product
macros/preparation and excludes unreported fortification doses; classification
artwork alone cannot establish nutrition.

Every refresh audits all retained SKUs and all national reference rows with
`audit_food_quality.py`. Physically impossible per-100-g nutrient amounts are
quarantined, with their source values retained in the audit. Cross-field and
cross-reference disagreements are review flags, not automatic replacements.
Same-barcode agreement across markets is consistency of one underlying source,
not independent corroboration.

The release gate checks reported-nutrition provenance, hashes, byte sizes, row
counts and SQLite integrity. Legacy apps retain their immutable compatible
manifest while current apps receive schema 4.
