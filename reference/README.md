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

Rebuild the generic catalog, including these additions, with:

```sh
python3 Scripts/build_reference_foods.py \
  --base-catalog Akari/ReferenceFoods.json \
  --usda-supplement FoodIndex/reference/usda-sr-legacy-170273.json \
  --usda-supplement FoodIndex/reference/usda-sr-legacy-173468.json \
  --output Akari/ReferenceFoods.json
python3 Scripts/build_reference_food_index.py \
  --source Akari/ReferenceFoods.json --output Akari/ReferenceFoods.sqlite
```

Also pass `--usda-supplement` when refreshing the full USDA inputs. The importer
records the raw response's hash and refuses to replace an existing identity
with different data or import a branded product as a generic supplement.
The chocolate addition is not in the curated verification list; salt is.
