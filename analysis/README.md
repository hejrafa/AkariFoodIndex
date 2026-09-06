# Full catalog quality audit — 6 September 2026

The official JSONL export was scanned to completion (over 4.7 million source records). The nine market databases retain **1,452,796 SKU rows**, representing **1,417,681 unique barcodes**. All retained rows and all **21,510 national reference foods** were audited. Manufacturer checks were targeted at ambiguous product lines; this is not independent verification of every branded product.

## Results

- **1,029,250** market rows have an identified food type; **779,366** map to a specific supported 3D icon.
- **9,702** official category descendants and **21,317** exact multilingual labels extend the 111 owned food types. Ambiguous identities stay unresolved; categories with no suitable artwork keep the neutral icon.
- **1,255** direct category-to-Ciqual links agree with the current national table's actual French food name. Proxy links and mismatching/outdated codes were rejected.
- **44,899** branded market rows have one specific reference link; **15,450** have compatible calories/macros. These are candidates, not a count of applied estimates: the app additionally checks food identity, preparation, fortification and source errors.
- **8,330** reported micronutrient/reference comparisons were made on macro-compatible linked foods. Differences are flagged for review, never silently overwritten. **201** exact-name pairs across different national sources were also compared; definitions and preparation can legitimately differ.
- **14,310** rows report at least ten tracked micronutrients. Missing nutrients remain unknown unless a suitable, attributed reference estimate can fill them.
- **7,964** physically impossible per-100-g nutrient values were removed from the downloadable catalog. Original values and validation flags are preserved in the audit. Other inconsistent records retain validation flags and rank below otherwise equally relevant clean records.
- **35,115** repeated-barcode comparisons across markets found no nutrient conflicts. These records share an upstream source and are not independent corroboration.

| Market | SKU rows | Identified food type | Specific artwork |
|---|---:|---:|---:|
| AT | 18,234 | 11,181 | 8,140 |
| AU | 64,920 | 45,748 | 35,994 |
| CA | 104,125 | 71,543 | 56,343 |
| CH | 84,747 | 53,054 | 38,858 |
| DE | 230,620 | 147,184 | 104,155 |
| GB | 144,933 | 107,845 | 83,521 |
| IE | 64,147 | 36,852 | 30,315 |
| NZ | 12,644 | 9,432 | 7,211 |
| US | 728,426 | 546,411 | 414,829 |

Coverage is not accuracy. Counts are per market unless explicitly identified as unique barcodes; no before/after accuracy improvement is inferred from the larger catalog.

## Concrete corrections

Both US Babybel Plus (`0041757023263`) and UK “Plus vitamins” / Babybel (`3073781178227`) now resolve to cheese, including when upstream categories are absent. Manufacturer evidence separates Plus vitamin/probiotic products from current PRO and Original products. A compatible reduced-fat cheese reference can estimate baseline minerals; unreported added vitamins are excluded, and existing label values always win.

Search uses the most specific category translations while retaining all-query-term matching. “Babybel Edamer” can find a categorised Edam product; “Fol Epi” still excludes Folgers. Broad brands such as Alpro, Barilla and Biscoff use the actual product category so their different food types do not inherit one brand-wide icon.

## Reported versus estimated nutrition

The flat CSV was rejected after the Paniermehl (`20003159`) check showed upstream recipe estimates leaking into ordinary nutrient columns. That diagnostic is preserved as `csv-diagnostic-audit-2026-09-06.json`, explicitly marked unusable for reported-nutrient coverage.

Production imports use the official JSONL: packaging/manufacturer input sets, as sold, with explicit amount and nutrient units. Aggregated recipe estimates, computed-only values, percent-DV amounts, and guessed mass/volume conversions are excluded. Legacy JSON's separate `nutriments` object remains supported; `nutriments_estimated` is ignored. Reported zero is preserved. A release gate rejects CSV/unverified provenance, empty markets, hash/count mismatches and corrupt SQLite files.

## Reproduction and source trail

- `full-quality-audit-2026-09-06.json`: complete coverage, missing fields, quarantine originals, reference disagreements and bounded unresolved examples.
- `taxonomy-audit-2026-09-06.json`: category coverage, rejected nutrient links and source hashes.
- `research-sources-2026-09-06.json`: original 12.8 GB source hash/version and manufacturer/documentation URLs with explicit evidence limits.
- `babybel-source-2026-09-06.json`: live source records and unavailable barcode response.
- `legacy-classification-audit.md`: historical schema-1 audit; its rollout status and counts describe the earlier snapshot.

```sh
python3 FoodIndex/build_index.py --off-export openfoodfacts-products.jsonl.gz --market DE=en:germany --output-dir dist
python3 FoodIndex/audit_food_quality.py dist --references Akari/ReferenceFoods.sqlite --reclassify --output audit.json
python3 FoodIndex/verify_release.py dist
python3 -m unittest discover -s FoodIndex -p 'test_*.py'
```

In the standalone food-index repository, omit the `FoodIndex/` script prefix and supply the separately checked-out reference database. The scheduled refresh performs this audit before publication. Source-specific licensing remains in `../LICENSE.md`.
