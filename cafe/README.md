# Café catalog audit — 6 September 2026

Akari now bundles a café-specific catalog alongside its national tables and Open Food Facts. It contains 216 generic recipe/average entries and 1,161 Starbucks Germany drink–milk–size entries. These counts include variants, not distinct drink families. No new server or API subscription is required. The public FoodIndex release is unchanged; this catalog ships with the app.

## Sources and decisions

- **FSANZ AUSNUT 2023**: official food nutrient profiles (per 100 g), recipes and measures, downloaded from https://www.foodstandards.gov.au/science-data/food-nutrient-databases/ausnut/data-files. Selected factual rows are retained in `ingredients.json`, with Survey ID, public food key and derivation. Source-backed espresso, long black, instant coffee, Turkish coffee and chai powder drinks retain their identities.
- **USDA FNDDS 2710375**: brewed black coffee and its existing 240 g cup portion, from the app’s reference catalog. Pour-over, filter and French press are search aliases for this generic brewed-coffee average, not independently analyzed brewing methods.
- **Japan MEXT 2023, food 16035**: matcha powder macros and micronutrients. Caffeine is explicitly supplemented from Japan MAFF’s published 3.2 g/100 g (= 3,200 mg/100 g) matcha value: https://www.maff.go.jp/j/syouan/seisaku/risk_analysis/priority/hazard_chem/caffeine.html. A 2 g matcha recipe therefore contributes 64 mg caffeine. Missing matcha nutrients, including sugar, remain unknown in mixtures.
- **Starbucks Germany**: the nutrition page linked the 22 April 2026 PDF when checked on 6 September 2026: https://www.starbucks.de/de/nutrition/. The exact PDF URL, SHA-256, dates and 1,395 extracted relevant source rows are in `starbucks-de.json`. The bundled core catalog excludes seasonal banana/coconut-water recipes, leaving 1,161 entries. Each named size stays independent, including regular, Blonde and decaf recipes. Salt g is converted to sodium mg using g × 400; other unreported micronutrients are absent. This is German menu data, not US or worldwide Starbucks nutrition.

## Generic recipe policy

`Scripts/build_cafe_catalog.py` defines explicit ingredient weights. For example, a flat white uses 60 g espresso and 120 g milk; a cappuccino uses 30 g espresso and 120 g milk; a latte uses 30 g espresso and 210 g milk. These are editable **Akari estimates**, not FSANZ-analyzed versions of those exact recipes and not universal café standards. Ingredients are assumed to retain their weight/nutrients; heating losses and evaporation are not modeled. No automatic verified badge is granted.

Oat uses the actual unfortified AUSNUT oat beverage; soy, almond, coconut drink, skim, low-fat, whole and lactose-free milk each have their own source ingredient. Grouped rice/oat or almond/coconut averages are never relabeled as an individual milk. Ingredient fortification and brands can materially change a real drink. Mocha explicitly includes cocoa and sugar; the other calculated lattes have no added syrup/sugar. The separately named sweetened chai-powder record is distinct from brewed, unsweetened chai recipes.

Mixtures calculate a nutrient only when **every ingredient** declares it. Absent iodine, sugar or vitamins are not filled with zero; a gap is filled only through the reference rows' marked fills (`FoodIndex/nutrient-fills/`). Source energy is retained (kJ / 4.184 for AUSNUT), not recomputed from rounded macros. Caffeine is an average: different beans, extraction and shot sizes vary substantially.

Generic recipes offer editable ml/l and gram amounts. `liquid-measures.json` pins
28 liquid density facts (with measure IDs and workbook hash) from FSANZ's
AUSNUT 2023 Food measures. The builder sums the liquid ingredient volumes using
those densities; the USDA brewed coffee reference uses 1 g/ml. Matcha's 2 g of
powder stays in the nutritional mass while prepared volume is approximated by
its water/milk volume (only recipes with at most 2% matcha qualify). This excludes
unmeasured powder displacement and foam. Mocha recipes use the finished mocha
reference (AUSNUT 11202013, 1.02 g/ml), rather than adding dry cocoa/sugar bulk
volumes to a liquid. Iced recipe volumes describe liquid after ice melts.

All 216 generic drinks now have an explicitly approximate conversion. New café
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

## Verified counterparts — 30 October 2026

A generic drink counts as **verified** on the catalogue health board when every
ingredient is a curated reference row of the five national tables, the rule the
recipe catalogue follows. The AUSNUT ingredient rows are outside those tables,
so each was checked for a verified counterpart under the nutrient-fill
plausibility rule (same food, calories within 15 %, protein, fat and
carbohydrates within 3 g per 100 g). `ingredients.json` records the result on
every ingredient the recipes use: a `reference` (the verified row, the day it
was checked, the comparison, and `fills` for a nutrient the row does not declare,
such as a milk's caffeine, taken from the AUSNUT row it stood for) or a
`referenceCheck` saying why none fits. `Scripts/build_cafe_catalog.py` builds
such an ingredient from the reference row's nutrients in the bundled index, keeps
the AUSNUT id as `measureID` for the liquid measure, names the tables in the
record's attribution and lists the reference ids under `ingredients`; the build
stops on a reference that is missing or not verified.

Mapped: tap water → USDA 2710706 water; whole milk → BLS M111300; skim milk →
BLS M111100; reduced-fat milk → BLS M111200 (1.5 %); lactose-free whole milk →
BLS M114300; sugar → Ciqual 31016; and since 30 October 2026 espresso → USDA
2710378 and decaf espresso → USDA 2710379, both made curated references for
it, with their iodine filled from the AUSNUT rows and marked because USDA
states none. USDA brewed coffee and tonic water were reference rows already.
Kept on AUSNUT, with the reason in the file: prepared instant coffee, the long
blacks and Turkish coffee, the chai-powder latte, brewed chai, oat, soy,
almond and coconut drinks (the tables' products differ by more than 15 % in
energy), cocoa powder (fat differs by 4.6 g) and matcha (MEXT 16035 is not a
curated reference). So 74 of the 216 generic drinks are verified: black
coffee, espresso, double and decaf espresso, iced americano and espresso
tonic, and every espresso drink with a cow's milk (flat white, cappuccino,
latte, cortado, piccolo, macchiatos, café au lait, iced latte and iced flat
white, regular and decaf); the plant-milk drinks, mochas, matcha and chai
drinks wait on their ingredients.

## Coverage limits

This is substantial core café coverage, not every possible café drink, custom syrup, roast, country or chain. Generic cold brew, ristretto and lungo are not relabeled from brewed coffee/espresso without suitable source-specific values. Starbucks cold brew is available under Branded. Other chains continue to come from Open Food Facts until a reviewed official menu source is imported. Recipes and their attribution are shown in food details; diary entries retain logged values and artwork, as with existing foods.

## Rebuild and verification

```
python3 Scripts/build_cafe_catalog.py
python3 -m unittest discover -s Scripts -p 'test_cafe_catalog.py'
```

`ingredients.json`, `liquid-measures.json`, and `starbucks-de.json` are the reviewed input facts, not generated nutrition guesses. `Scripts/import_cafe_sources.py` can reproduce their source extraction from locally downloaded official workbooks and PDF (openpyxl/pdfplumber required). Review source changes before regenerating. `CafeDrinkCatalogTests` exercises offline coverage, strict milk/brand matching, group pagination, independent brand portions, matcha units, artwork, and HealthKit quantity metadata/relogging. See `Akari/CafeData-LICENSE.txt` for source reuse/attribution.

## Verified counterparts, second pass (30 October 2026, evening)

On the architect's instruction of 30 October 2026 the six AUSNUT ingredients
that failed the 15 % rule are mapped to the verified row of the same food in
the same state anyway, because the drink's values then come from that
measured row and the AUSNUT value is no longer used: oat beverage 20103001 →
BLS C660000 (the oat-drink family's median serving falls from 38.7 to
22.3 kcal per 100 g, 54 → 29 kcal for the drink itself), soy beverage
20101002 → USDA 2705405 (42.5 → 28.3; 59 → 38), almond beverage 20105001 →
BLS H800000 (13.4 → 19.0; 16 → 24), coconut beverage 20105006 → USDA 2705413
(19.9 → 23.7; 25 → 31), cocoa powder 11904001 → BLS S711000 (mochas with cow's
milk 61.2 → 62.2; the powder 319 → 365 kcal) and brewed chai 11101004 → USDA
black tea 2710488 (chai lattes 24.9 → 25.2). The AUSNUT values each reference
lacks (caffeine, iodine, selenium, vitamin C) are filled and marked, as the
espresso rows' iodine was. MEXT matcha 16035 is a curated reference itself
(17 nutrients; the app's thin-row list names it), so the 19 matcha drinks keep
their values. Instant coffee 11201001 maps to Ciqual 18073 and decaf instant
11203001 to BLS N440100, both within the rules. The long blacks, the sweetened
Turkish coffee and the powder chai latte had AUSNUT recipe rows with no
counterpart; they are now built from verified parts in
`build_cafe_catalog.py`: espresso and water (30 + 220 g, 60 + 190 g, decaf
30 + 220 g), espresso, water and sugar (40 + 16 + 4 g) and 20 g of Akari's
chai latte powder generic (`FoodIndex/reference/akari-label-chai-latte-powder.json`,
three supermarket labels) in 230 g whole milk; that drink declares no water,
since labels state no moisture. With this every one of the 216 generic drinks
is verified: `dishes.cafe.verified` equals `dishes.cafe.generic`.

## Barista oat drink (30 October 2026, b216 follow-up)

Cafés pour barista oat drinks, not the unsweetened retail oat drink: Oatly
Barista Edition, Alpro Barista Hafer, dmBio, enerBiO and Alnatura Barista
state 50 to 61 kcal per 100 ml, the BLS C660000 row 29 kcal, so an oat latte
on the BLS row was undercounted by about a third. The oat ingredient now maps
to `akari:label:oat-drink-barista` (FoodIndex/reference), the median of those
five labels: 54 kcal, 2.0 g fat, 6.7 g carbohydrate, 3.4 g sugar, 1.1 g
protein, 52 mg sodium per 100 ml, with the AUSNUT row's caffeine and water filled and marked as before; the plain oat drink staple
keeps BLS C660000 and the barista generic is a plant-based staple of its own.
Per 100 ml the other milks' barista labels sit within the 15 % rule of the
measured rows and stay: Alpro Barista Sojadrink 42 kcal against USDA 2705405
at 38; Alpro Barista Mandel 24 and Natumi Mandeldrink Barista 19 against BLS
H800000 at 24; Alpro Barista Kokosnuss 33 against USDA 2705413 at 31.
