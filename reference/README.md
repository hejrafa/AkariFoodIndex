# Reviewed source additions

`usda-sr-legacy-170273.json` is the unmodified USDA FoodData Central API response
for FDC 170273 / NDB 19904, retrieved September 27, 2026:

- Source: https://api.nal.usda.gov/fdc/v1/food/170273 (public API key required)
- Identity: Chocolate, dark, 70–85% cacao solids, SR Legacy, published April 1, 2019.
- License: USDA public-domain food composition data (CC0).

This is a generic range, not an exact branded 85% chocolate label. Keep that
range in the displayed identity. The source supplies 1 oz (28.35 g) and 1 bar
(101 g); a missing user amount remains an editable suggested portion.

`usda-sr-legacy-173468.json` is the unmodified USDA FoodData Central API response
for FDC 173468, retrieved October 16, 2026:

- Source: https://api.nal.usda.gov/fdc/v1/food/173468 (public API key required)
- Identity: Salt, table, SR Legacy, published April 1, 2019.
- License: USDA public-domain food composition data (CC0).

None of the five national tables carries plain table salt. This row is the
verified answer for "salt" and "Salz"; it has no energy, so the verification
policy names it as a reviewed zero-calorie reference, like plain water.

`akari-label-beef-protein-isolate.json` is Akari's first reviewed generic built
from typical labels (source `akariLabel`, shown as "Akari, from typical labels"),
written October 28, 2026:

- Identity: plain, unflavoured beef protein isolate powder, id
  `akari:label:beef-protein-isolate`, one 30 g scoop.
- Values per 100 g: the median of three unflavoured labels (Bulk Beef Protein
  Isolate 97 Unflavoured, Hunter & Gather Beef Protein Unflavoured, Promix
  Unflavored Grass-fed Beef Protein Isolate), each listed in the file with
  where and when it was read, plus the labels left out and why.

None of the five national tables carries beef protein isolate. A label declares
energy, fat, saturates, carbohydrate, sugars, protein and salt, never eight
micronutrients, so the verification policy waives its micronutrient minimum
for this source alone; every other check stays. The importer recomputes each
median (a value enters only when at least three labels declare it; salt in g
× 400 is sodium in mg), refuses a file whose stated values differ from its
labels, and never replaces an existing identity.

Rebuild the generic catalog, including these additions, with:

```sh
python3 Scripts/build_reference_foods.py \
  --base-catalog Akari/ReferenceFoods.json \
  --usda-supplement FoodIndex/reference/usda-sr-legacy-170273.json \
  --usda-supplement FoodIndex/reference/usda-sr-legacy-173468.json \
  --label-generic FoodIndex/reference/akari-label-beef-protein-isolate.json \
  --output Akari/ReferenceFoods.json
python3 Scripts/build_reference_food_index.py \
  --source Akari/ReferenceFoods.json --output Akari/ReferenceFoods.sqlite
```

Also pass `--usda-supplement` and `--label-generic` when refreshing the full
inputs. The importer records each file's hash and refuses to replace an
existing identity with different data or import a branded product as a generic
supplement. The chocolate addition is not in the curated verification list;
salt and beef protein isolate are.
