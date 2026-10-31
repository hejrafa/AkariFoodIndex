# AkariFoodIndex

This pipeline publishes two deliberately separate kinds of SQLite food data:

- market-specific Open Food Facts product and barcode indexes; and
- Akari's generic-food reference index built from BLS, USDA FoodData Central,
  UK CoFID, French Ciqual, and Japan MEXT composition tables.

Keeping the ODbL product layer separate from the national reference tables
preserves source provenance and keeps each database's licence unambiguous.

The app checkout also holds a separate reviewed [café catalog](cafe/README.md)
with AUSNUT/MEXT ingredient recipes and Starbucks Germany menu facts. It is
bundled in the app and is not mixed into the ODbL release or used for automatic
packaged-food nutrient enrichment. Rebuild it with `Scripts/build_cafe_catalog.py`.

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

The Akari app checkout’s `FoodIndex/` folder is the source of truth and is
published unchanged as the root of the standalone AkariFoodIndex repository by
the app’s `Scripts/publish_food_index.py`. Commands below use the app
checkout’s `FoodIndex/` prefix. In the standalone repository, omit that prefix.

Stream the official compressed Open Food Facts JSONL export directly into the
builder so the multi-gigabyte source does not consume local disk space:

```sh
curl --fail --location \
  https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz | \
python3 FoodIndex/build_index.py --off-export - --off-export-gzip \
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
and curated verification coverage for every national source are checked again
here before it is published. National-table rows do not become verified merely
because they have many nutrients.

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
   an item of one of Akari's chain menus (`chains/*.json`,
   `cafe/starbucks-de.json`) and whose values per 100 g are the chain's
   published ones (calories within 10 % or 10 kcal, fat, carbs and protein
   each within 15 % or 1.5 g; items under 50 kcal per 100 g never count,
   since a drink's few kilocalories match anything) stays out when its brand
   is not that chain, the name is not the brand's own product that the chain
   merely sells (a Coca-Cola on a Burger King menu), and nobody has scanned
   it in the market. Menu names made only of generic food words
   ("Cheeseburger", "Blueberry muffin", "Caffè latte") never claim another
   maker's product; a name needs at least one word that is no word of Akari's
   staples, recipes or café drinks ("Big Mac", "Whopper", "Zinger"). A product
   that merely shares a menu item's name keeps its own label and stays.

The rule constants sit together at the top of `build_index.py`
(`ENERGY_TOLERANCE_SHARE` … `CHAIN_MATCH_MACRO_GRAMS`), and
`chains/menu-claims.json` is rule 4's finished claim list (every menu name that
can identify a copy, with its chain key, chain name and four values per 100 g,
the generic names already left out and the constants repeated under `rules`),
written by `python3 FoodIndex/build_index.py --menu-claims`; the live-search
worker fetches it from the mirror and applies the same four rules to the
products the app's online search returns. It is regenerated whenever a chain
file, the staples, the recipes or the café drinks change; `test_index.py`
checks that the committed file is current.

Counts from the German market built locally on 31 October 2026 from the
export of that day: 236,456 SKUs passed the market rule,
18,610 of them (7.9 %) were kept out and 217,846 SKUs in
197,900 families went into the pack.

| Rule | Removed | Examples from `rejected-de.jsonl` |
| --- | ---: | --- |
| Implausible nutrition, energy | 4,528 | Bahlsen Hit, 514 kcal declared, 700 from the macronutrients; Dae Joo Koreanisches Chilipulver, 181 against 292; International Cuisine cheese & bacon mini pizza, 101 against 234; Sponser Electrolyte Cherry, 200 against 62; Foodspring EAA, 254 against 188 |
| Implausible nutrition, above 100 g | 73 | 4820039840141 Oatflakes with strawberry (Ovsyanushka), carbs above 100 g per 100; 4050044774692 Zero creamer caramel macchiato (Starbucks), fat above 100 g per 100 |
| Unbranded, unscanned stub | 14,009 | 4010636032814 Jambon cuit chaud (completeness 0.20); 4316268628648 Lasagne Bolognese (0.38); 8856366002965 Extra Roll Seaweed (0.28); 4260562094022 No sugar chocolate bar (0.20); 4262397160958 QLF tastatur milchcreme mandel (0.20) |
| Another company's menu item | 0 | none in the German export of that day; the rule exists for copied menu values such as a "Big Mac" at McDonald's 235 kcal, 12 g fat, 18 g carbs and 12 g protein under another brand |

The first run of the rules, the same day, had rejected 6,032 products for
their energy and 24 as menu items: a third of the energy rejections were
drinks with undeclared alcohol (wines, an Alt beer declared per 100 g with
only a beverage category) and sugar-free sweets with undeclared polyols,
which the exceptions above now excuse, and every one of the 24 menu-item hits
was a product that merely shared a name with a chain item (Klassik, Bremer,
Caffè Crema), which is why rule 4 now also demands the chain's published
values and a substantial item. The "Big Mac bowl" that started the rule
(0002015950271) turned out to be a real product of an Irish meal-prep company
with its own nutrition, listed only for Ireland; it had reached the app
through the live Open Food Facts search, which now applies the same rules in
the worker.

## Verify

```sh
python3 -m unittest FoodIndex/test_index.py
```

Open Food Facts data is licensed under ODbL 1.0. Reference-table terms range
from CC0 to attribution licences and are listed in `LICENSE.md`. Product images
have separate CC BY-SA terms. Keep attribution visible and review the upstream
reuse guidance before changing distribution or contribution behavior.

## Publishing

`.github/workflows/refresh.yml` (`FoodIndex/.github/workflows/refresh.yml` in
the app checkout) is the complete distribution workflow. It
refreshes the core German-speaking and English-speaking markets weekly,
validates the independent generic-food reference database, verifies every
SQLite file and SHA-256 digest, then publishes the same files twice: to
Cloudflare R2 first, then as GitHub Release assets. Each copy's manifests point
at its own host.

- `https://foods.joinakari.com/latest/` is what the app reads:
  `manifest-v4.json`, `manifest.json` and the files they name, replaced every
  week. It is the R2 bucket `akari-food-index` (EU jurisdiction); the manifests
  are uploaded after their files.
- `https://foods.joinakari.com/releases/<tag>/` holds an immutable snapshot of
  each release. The newest three are kept; older ones are deleted at the end of
  the run.
- The [`hejrafa/AkariFoodIndex`](https://github.com/hejrafa/AkariFoodIndex)
  releases carry the same files. App builds from before the move still read
  them, so the GitHub release stays the archive until the next app build has
  reached testers.

The R2 steps need the repository secrets `CLOUDFLARE_API_TOKEN` (with Account >
Workers R2 Storage > Edit) and `CLOUDFLARE_ACCOUNT_ID`. Without them the run
stops before either copy changes. The upload refuses a `dist/` larger than 3 GB.

## Food classification and artwork

`artwork-classification.json` is the owned presentation taxonomy. After changing
it, the category taxonomy, serving identities, or classification fixtures, run
`python3 Scripts/sync_food_index_data.py` from the app checkout to refresh the
app's copies; shared regression fixtures and CI check that both implementations
stay aligned. Source category
IDs are matched exactly. Manufacturer-reviewed product-line rules include URLs,
review dates, and narrow name qualifiers. Nutrient and alcohol logic is separate.

Rules can declare `ingredientCategories`: when both occur in a food name, the
finished form owns its ingredient or flavor (for example peanut butter cookies,
chocolate milk, or protein bars). The same relationship resolves broad category
and alternate-name hints. Exact food terms before commas retain catalog wording
such as “Chocolate, milk” when there is a known ingredient relationship; powder
and other preparation identities are still considered. Shared fixtures cover
both directions and ambiguous German terms such as Eiweiß.

Generic and explicit chocolate bars use the existing 3D chocolate-bar icon from
the Microsoft Fluent Emoji set. The artwork manifest and license are unchanged.

`classify_artwork.py` writes each SKU's category, artwork ID, evidence, source, and
rule version. `audit_classification.py` produces coverage counts and a review
queue including unknown identities and known types with no suitable artwork.
See `analysis/README.md` for the initial nine-market audit and its limitations.

Releases expose `manifest-v4.json` and `*-v4.sqlite` for classified catalogues.
`prepare_release.py` preserves the legacy `manifest.json` with immutable URLs to
the previous compatible catalogues, so older app versions keep working. The
app falls back to legacy only if the new manifest has not been published (404).
Do not delete the pinned legacy release while supporting those clients: both
copies' `manifest.json` still point at it, because R2 holds only schema 4.

Run all builder, classification, and compatibility checks:

```sh
python3 -m unittest discover -s FoodIndex -p 'test_*.py'
```

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
ANSES table. Proxy links and unspecified averages are excluded. The app still
requires compatible product macros/preparation and excludes unreported
fortification doses; classification artwork alone cannot establish nutrition.

Every refresh audits all retained SKUs and all national reference rows with
`audit_food_quality.py`. Physically impossible per-100-g nutrient amounts are
quarantined, with their source values retained in the audit. Cross-field and
cross-reference disagreements are review flags, not automatic replacements.
Same-barcode agreement across markets is consistency of one underlying source,
not independent corroboration.

The release gate checks reported-nutrition provenance, hashes, byte sizes, row
counts and SQLite integrity. Legacy apps retain their immutable compatible
manifest while current apps receive schema 4.
