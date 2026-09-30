# Café catalog audit — 6 September 2026

Akari now bundles a café-specific catalog alongside its national tables and Open Food Facts. It contains 213 generic recipe/average entries and 1,161 Starbucks Germany drink–milk–size entries. These counts include variants, not distinct drink families. No new server or API subscription is required. The public FoodIndex release is unchanged; this catalog ships with the app.

## Sources and decisions

- **FSANZ AUSNUT 2023**: official food nutrient profiles (per 100 g), recipes and measures, downloaded from https://www.foodstandards.gov.au/science-data/food-nutrient-databases/ausnut/data-files. Selected factual rows are retained in `ingredients.json`, with Survey ID, public food key and derivation. Source-backed espresso, long black, instant coffee, Turkish coffee and chai powder drinks retain their identities.
- **USDA FNDDS 2710375**: brewed black coffee and its existing 240 g cup portion, from the app’s reference catalog. Pour-over, filter and French press are search aliases for this generic brewed-coffee average, not independently analyzed brewing methods.
- **Japan MEXT 2023, food 16035**: matcha powder macros and micronutrients. Caffeine is explicitly supplemented from Japan MAFF’s published 3.2 g/100 g (= 3,200 mg/100 g) matcha value: https://www.maff.go.jp/j/syouan/seisaku/risk_analysis/priority/hazard_chem/caffeine.html. A 2 g matcha recipe therefore contributes 64 mg caffeine. Missing matcha nutrients, including sugar, remain unknown in mixtures.
- **Starbucks Germany**: the nutrition page linked the 22 April 2026 PDF when checked on 6 September 2026: https://www.starbucks.de/de/nutrition/. The exact PDF URL, SHA-256, dates and 1,395 extracted relevant source rows are in `starbucks-de.json`. The bundled core catalog excludes seasonal banana/coconut-water recipes, leaving 1,161 entries. Each named size stays independent, including regular, Blonde and decaf recipes. Salt g is converted to sodium mg using g × 400; other unreported micronutrients are absent. This is German menu data, not US or worldwide Starbucks nutrition.

## Generic recipe policy

`Scripts/build_cafe_catalog.py` defines explicit ingredient weights. For example, a flat white uses 60 g espresso and 120 g milk; a cappuccino uses 30 g espresso and 120 g milk; a latte uses 30 g espresso and 210 g milk. These are editable **Akari estimates**, not FSANZ-analyzed versions of those exact recipes and not universal café standards. Ingredients are assumed to retain their weight/nutrients; heating losses and evaporation are not modeled. No automatic verified badge is granted.

Oat uses the actual unfortified AUSNUT oat beverage; soy, almond, coconut drink, skim, low-fat, whole and lactose-free milk each have their own source ingredient. Grouped rice/oat or almond/coconut averages are never relabeled as an individual milk. Ingredient fortification and brands can materially change a real drink. Mocha explicitly includes cocoa and sugar; the other calculated lattes have no added syrup/sugar. The separately named sweetened chai-powder record is distinct from brewed, unsweetened chai recipes.

Mixtures calculate a nutrient only when **every ingredient** declares it. Absent iodine, sugar or vitamins are not filled with zero. Source energy is retained (kJ / 4.184 for AUSNUT), not recomputed from rounded macros. Caffeine is an average: different beans, extraction and shot sizes vary substantially.

Generic recipes offer editable ml/l and gram amounts. `liquid-measures.json` pins
28 liquid density facts (with measure IDs and workbook hash) from FSANZ's
AUSNUT 2023 Food measures. The builder sums the liquid ingredient volumes using
those densities; the USDA brewed coffee reference uses 1 g/ml. Matcha's 2 g of
powder stays in the nutritional mass while prepared volume is approximated by
its water/milk volume (only recipes with at most 2% matcha qualify). This excludes
unmeasured powder displacement and foam. Mocha recipes use the finished mocha
reference (AUSNUT 11202013, 1.02 g/ml), rather than adding dry cocoa/sugar bulk
volumes to a liquid. Iced recipe volumes describe liquid after ice melts.

All 213 generic drinks now have an explicitly approximate conversion. New café
servings use practical defaults: nearest 25 ml for drinks of at least 100 ml,
nearest 5 ml for smaller drinks. Nutrition is scaled to that displayed volume;
we do not display a rounded amount while secretly logging the original recipe
mass. Saved quantities retain both physical dimensions and the estimate flag.
The product header shows correctly converted nutrition per 100 ml. The picker
keeps whole numbers in the left column and units on the right. Only units that
need fractions have a separate middle column of fixed choices. Unit changes
round to those choices, with nutrition recalculated for the displayed quantity.
Starbucks remains count-only because the imported source gives per-serving
facts without a measured finished-drink mass or volume. Dry matcha and other
powders do not acquire drink units from their names or icons.

Coffee and tea/matcha carry explicit artwork identities, independent of whether their names contain “milk”. Searches understand oatmilk/soymilk, common cappuccino misspellings, and German milk terms. Milk and brand words constrain results. Generic and branded pages paginate separately and remain available offline.

## Coverage limits

This is substantial core café coverage, not every possible café drink, custom syrup, roast, country or chain. Generic cold brew, ristretto and lungo are not relabeled from brewed coffee/espresso without suitable source-specific values. Starbucks cold brew is available under Branded. Other chains continue to come from Open Food Facts until a reviewed official menu source is imported. Recipes and their attribution are shown in food details; diary entries retain logged values and artwork, as with existing foods.

## Rebuild and verification

```
python3 Scripts/build_cafe_catalog.py
python3 -m unittest discover -s Scripts -p 'test_cafe_catalog.py'
```

`ingredients.json`, `liquid-measures.json`, and `starbucks-de.json` are the reviewed input facts, not generated nutrition guesses. `Scripts/import_cafe_sources.py` can reproduce their source extraction from locally downloaded official workbooks and PDF (openpyxl/pdfplumber required). Review source changes before regenerating. `CafeDrinkCatalogTests` exercises offline coverage, strict milk/brand matching, group pagination, independent brand portions, matcha units, artwork, and HealthKit quantity metadata/relogging. See `Akari/CafeData-LICENSE.txt` for source reuse/attribution.
