# Food identity and artwork audit — 6 September 2026

Akari was choosing artwork from the displayed name alone. The released packaged-food databases use schema 1, which omits Open Food Facts generic names and category tags. The app already requests these fields for live results, but the thumbnail did not use them. That explains why “Fol Epi Classic” got a plate even though its upstream records identify it as cheese.

## Scope and findings

- Scanned all **734,248 retained SKU records** across nine published market databases (**681,304 families**). Counts are per market; the same barcode can appear in several markets.
- None of those schema-1 databases retain category tags. This is a pipeline omission, not evidence that the upstream products lack categories.
- Checked 11 live records spanning Fol Epi, Babybel, Boursin, Leerdammer, and Philadelphia. All 11 contain cheese categories and all 11 resolve to cheese with the new rules. Further API requests received HTTP 429; they remain recorded as failures and are excluded from this check.
- Reviewed Fol Epi’s manufacturer pages for Classic, Légère, the Scheiben range, and Extra fines. All **28 Fol Epi records in the German catalogue** now resolve to cheese using the available name/brand metadata.
- Broader brands cannot safely identify food type: the catalogue contains Oreo cookies and cereal, Biscoff ice cream and chocolate, Alpro drinks and yogurt alternatives, and Barilla pasta and sauce. These need product-level categories, not a brand-wide icon.

## Owned classification layer

`artwork-classification.json` defines **111 food types**, 160 exact source taxonomy tags, multilingual food-name aliases, and **7 manufacturer-reviewed product lines**. The identical rules run in the app and index builder. Each decision stores category, icon ID, source, evidence, and rule version.

The decision order is source category tags, generic identity, exact category labels, narrowly reviewed product-line names, then food-name aliases. Explicit finished forms such as pizza or ice cream can override incomplete broad ingredient tags. Equal-priority conflicts remain unresolved. Product-line matching requires the remainder of the name to contain only reviewed qualifiers, so “Fol Epi sandwich” stays a sandwich and an unknown new product is not guessed.

Classification is presentation-only. It does not change nutrient values, inferred nutrition, allergens, alcohol counts, or the verified badge. The identity survives the hot cache, selection, detail, HealthKit food metadata, and relogging.

## Coverage on the existing, metadata-poor release

| Market | SKU records | Classified food type | Has specific artwork |
|---|---:|---:|---:|
| AT | 17,178 | 6,765 | 5,534 |
| AU | 11,877 | 7,966 | 6,315 |
| CA | 99,755 | 60,361 | 51,180 |
| CH | 82,882 | 34,551 | 29,719 |
| DE | 220,376 | 89,715 | 71,752 |
| GB | 139,733 | 89,708 | 76,463 |
| IE | 62,679 | 31,832 | 27,642 |
| NZ | 2,932 | 1,971 | 1,509 |
| US | 96,836 | 68,673 | 53,922 |

The new classification layer recognizes 391,542 records (53.3%) using the legacy metadata alone; 324,036 have a corresponding specific icon. Another 67,506 have a recognized food type but intentionally retain the neutral plate, including yogurt, sauces, oils, and several spreads. The older name-artwork fallback can still cover additional names; these figures measure the new classification layer, not total rendered icon coverage.

**These are coverage counts, not accuracy scores or a measured before/after uplift.** Only the targeted cheese sample was checked against live source categories. A fresh full export is needed to measure category-backed coverage across the entire catalogue.

## Index and rollout

- Schema 4 retains complete schema-3 identity/nutrition fields and adds `artwork_classification_json` per SKU plus a classification version in metadata.
- Each refresh writes `classification-audit.json`: coverage by type and evidence source, missing-artwork counts, and up to 200 unresolved/unsupported representative families per market for review.
- `manifest-v4.json` and `*-v4.sqlite` assets serve new apps. `manifest.json` remains compatible with older apps and pins their existing catalogue to immutable release URLs. New apps fall back to the legacy manifest only while v4 returns 404.
- The private Akari reference checkout continues using the repository’s existing deploy key. No app credentials or new server are introduced.
- This change prepares the builder and app; **the full source export has not been rebuilt or published during this audit**. The draft index update must be merged and its refresh completed before the app can download category-rich catalogues.

## Next data work

Run the updated export builder, review the generated queue, and measure category coverage from that release. Add exact product/barcode corrections only with recorded source evidence. Prioritize suitable artwork for yogurt, sauces, spreads, nuts, and crisps instead of disguising them as fruit, cheese, or fries. Avoid mass guesses from ingredient lists or multi-category brand names.

## Evidence and reproduction

- Catalogue snapshot: `catalog-20260906-6`, generated `2026-09-06T07:56:23Z`; raw counts and review candidates are in `catalogue-audit-2026-09-06.json`.
- Live source responses and failures: `branded-sample-2026-09-06.json` (Open Food Facts, ODbL-derived records; see `../LICENSE.md`).
- [Open Food Facts category tag schema](https://openfoodfacts.github.io/documentation/docs/Product-Opener/schemas/schemas/product_tags/).
- [Fol Epi Scheiben](https://ich-liebe-kaese.de/kaesemarken/fol-epi/produkte/fol-epi-scheiben/), [Classic](https://ich-liebe-kaese.de/kaesemarken/fol-epi/produkte/fol-epi-scheiben/fol-epi-scheiben-classic/), [Extra fines](https://ich-liebe-kaese.de/kaesemarken/fol-epi/produkte/fol-epi-extra-fines/).
- [Bel cheese products](https://www.belbrandsfoodservice.com/products/), [Leerdammer](https://www.leerdammer.de/unsere-produkte), [Philadelphia Original](https://www.philadelphia.co.uk/products/philadelphia-original?categoryId=18660), [Red Bull](https://www.redbull.com/us-en/energydrink), [Haribo Goldbears](https://www.haribo.com/en-ca/products/goldbears).
- [Biscoff product range](https://www.lotusbiscoff.com/en-us/products) illustrates why the same product-line name can refer to cookies or a spread.

```sh
python3 FoodIndex/audit_classification.py /path/to/release --output audit.json
python3 -m unittest FoodIndex/test_classification.py FoodIndex/test_index.py FoodIndex/test_release.py
```
