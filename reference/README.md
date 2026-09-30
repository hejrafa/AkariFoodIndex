# Reviewed source additions

`usda-sr-legacy-170273.json` is the unmodified USDA FoodData Central API response
for FDC 170273 / NDB 19904, retrieved September 27, 2026:

- Source: https://api.nal.usda.gov/fdc/v1/food/170273 (public API key required)
- Identity: Chocolate, dark, 70–85% cacao solids, SR Legacy, published April 1, 2019.
- License: USDA public-domain food composition data (CC0).

This is a generic range, not an exact branded 85% chocolate label. Keep that
range in the displayed identity. The source supplies 1 oz (28.35 g) and 1 bar
(101 g); a missing user amount remains an editable suggested portion.

Rebuild the generic catalog, including this addition, with:

```sh
python3 Scripts/build_reference_foods.py \
  --base-catalog Akari/ReferenceFoods.json \
  --usda-supplement FoodIndex/reference/usda-sr-legacy-170273.json \
  --output Akari/ReferenceFoods.json
python3 Scripts/build_reference_food_index.py \
  --source Akari/ReferenceFoods.json --output Akari/ReferenceFoods.sqlite
```

Also pass `--usda-supplement` when refreshing the full USDA inputs. The importer
records the raw response's hash and refuses to replace an existing identity
with different data or import a branded product as a generic supplement.
This addition does not promote the food into the curated verification list.
