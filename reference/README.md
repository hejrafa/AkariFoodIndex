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

`usda-sr-legacy-<fdcId>.json`, ten spice rows added 31 October 2026 for the
spice shelf after Rafael's nutrient floor (20 of 23 tracked nutrients) took the
BLS, Ciqual, CoFID and MEXT rows of these foods out of the verified list; each
is curated as its staple's verified row, the European rows stay as named
duplicates, and the one recipe on the BLS black pepper row points here:

- 170931 Spices, pepper, black (NDB 02030), the unmodified API response,
  https://api.nal.usda.gov/fdc/v1/food/170931, retrieved October 31, 2026.
- 170922 Spices, coriander seed (02013); 171315 Spices, allspice, ground
  (02001); 171324 Spices, fenugreek seed (02019); 170929 Spices, mustard seed,
  ground (02024); 170937 Spices, tarragon, dried (02041); 173471 Vanilla
  extract (02050); 170921 Spices, coriander leaf, dried (02012); 172239
  Spearmint, dried (02066), the Mint staple's dried state; 170075 Chives,
  freeze-dried (11615), the Chives staple's dried state. These nine are the
  rows' objects from USDA's own SR Legacy JSON dataset
  (https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_json_2018-04.zip,
  file dated April 24, 2025), written one per file on October 31, 2026, because
  the API's public key throttled after the first row; the dataset object is
  the API response without its empty `foodComponents` list and its valueless
  nutrient-group headers, so the imported values are identical. All SR Legacy,
  published April 1, 2019, CC0.
- Not taken, because USDA's rows are as thin as the ones they would replace:
  170919 cardamom (19 of 23 under the convention), 170936 savory (19), 171322
  dill weed, dried (18), 172241 balsamic vinegar (15); and USDA has no rice
  vinegar or mirin row at all. Those staples stay out until a table or a label
  generic carries them.

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
  $(for f in FoodIndex/reference/usda-sr-legacy-*.json; do printf -- '--usda-supplement %s ' "$f"; done) \
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

## Sports nutrition generics (30 October 2026)

`akari-label-<slug>.json` for 28 sports foods none of the five national tables
carries: whey protein isolate, clear whey, casein, pea, rice and hemp protein,
the vegan protein blend, mass gainer, the low-sugar protein bar, protein
cookie, high-protein pudding, protein pancake mix, protein porridge,
high-protein ice cream, energy gel, energy chews, amino acid powder (EAA or
BCAA), maltodextrin, cluster dextrin, recovery shake powder, peanut butter
powder, high-protein yogurt, protein granola, protein muesli, protein balls,
protein water, protein wafer and protein spread. Each file holds three labels
read on 30 October 2026 from Open Food Facts through Akari's own proxy
(`https://api.joinakari.com/v1/off/product/<barcode>`), the same source the
beef protein isolate's third label used, with the barcode, brand, product
name, ingredients where the entry states them and the per-100 g panel; the
file's `rule` says whether the labels are unflavoured (the plain powders) or
the makers' default flavours (bars, cookies, puddings, gels, chews and the
other foods that are only sold flavoured). Creatine, glutamine, beta-alanine
and electrolyte tablets have no generic because their labels declare no
energy, which the verification policy refuses; pre-workout, oat protein and
protein chips had fewer than three clean labels.

Rebuild with every file in the folder:

```sh
python3 Scripts/build_reference_foods.py \
  --base-catalog Akari/ReferenceFoods.json \
  $(for f in FoodIndex/reference/usda-sr-legacy-*.json; do printf -- '--usda-supplement %s ' "$f"; done) \
  $(for f in FoodIndex/reference/akari-label-*.json; do printf -- '--label-generic %s ' "$f"; done) \
  --output Akari/ReferenceFoods.json
```

## Supplement generics (30 October 2026)

`akari-label-<slug>.json` for 50 supplements as dm, Rossmann and pharmacies
sell them, one generic per supplement and common form: magnesium tablet, vitamin d3 tablet, vitamin d3 + k2 tablet, magnesium effervescent tablet, vitamin c depot capsule, zinc + vitamin c tablet, zinc + vitamin c effervescent tablet, vitamin c 1000 tablet, iron tablet, calcium + d3 tablet, multivitamin a–z tablet, children's multivitamin gummies, folic acid tablet, vitamin b complex tablet, vitamin b12 tablet, vitamin b12 effervescent tablet, magnesium + potassium tablet, electrolyte effervescent tablet, magnesium + calcium + d3 tablet, selenium tablet, immune effervescent tablet, immune complex tablet, pregnancy multivitamin, hair, skin and nails tablet, zinc tablet, senior multivitamin tablet, collagen powder, children's multivitamin chewable tablet, magnesium + calcium effervescent tablet, vitamin d3 + k2 drops, vitamin c lozenge, magnesium direct granulate stick, iron direct granulate stick, magnesium 500 depot tablet, collagen drink ampoule, multivitamin + mineral effervescent tablet, magnesium capsule, vitamin d gummy or chewable tablet, eye vitamin capsule, electrolyte powder stick, glucosamine joint tablet, vitamin c powder, vitamin c effervescent tablet, iron effervescent tablet, calcium effervescent tablet, calcium chewable tablet, vitamin d3 drops, immune direct stick, omega-3 fish oil capsule, omega-3 algae oil capsule. Each file
holds three or more labels read on 30 October 2026 from dm.de, rossmann.de or
shop-apotheke.com product pages (the page's URL, GTIN or PZN where the page
states it, ingredients, the pack's count and net weight and the declared
dose). A supplement label declares its dose per tablet, capsule, stick or
drop, so the file converts each declared value with the dose's weight (the
pack's net content divided by its count; drops and ampoules carry a density
in their serving note) and states it per 100 g of the product; the
`nutrients` are the medians of the labels that declare a value, and a value
enters only when three labels declare it. The twelve micronutrients Akari
tracks are the only ones a file carries; vitamin E, K, the B vitamins other
than B12 and folate, biotin, copper and the like stay in the serving notes.
A label that declares no energy and no macros adds nothing for them, and a
generic whose labels declare no energy stands at 0 kcal under the
verification policy's clause for label generics with a micronutrient; nothing
is zero-filled. The dose is the row's portion (1 tablet, 1 capsule, 1 drop,
1 stick, 2 gummies, one scoop). Generics that ended with fewer than three
usable labels and have no file: cod-liver-oil (1), collagen-effervescent (1), electrolyte-tablet (1), greens-powder (1), hair-vitamin-gummies (1), kids-multivitamin-syrup (2), magnesium-gummies (1), multivitamin-gummies (1), omega-3-algae-oil-capsule (2), omega-3-fish-oil-capsule (2), vitamin-c-1000-direct-granulate (2), vitamin-d-effervescent (1); the omega-3 capsules
and the probiotic, melatonin, biotin, vitamin E, K2 and herbal products
declare nothing Akari tracks and no energy. The scratch harvest with every
label read, including the skipped pages and why, is in the data session's
record of 30 October 2026.

### Oil capsules (30 October 2026)

`akari-label-omega-3-fish-oil-capsule.json` and `akari-label-omega-3-algae-oil-capsule.json`
take their fat and energy from labels that state the capsule's content as oil
(1,000 or 1,400 mg sea fish oil per capsule; 1,000 mg microalgae oil per two
capsules on the maker's page): the oil mass is the fat, its energy 9 kcal per
gram, and the oil carries 0 g carbohydrate and 0 g protein, the shell left
unstated. The labels with a full table (Mivolis and altapharma for both
generics) are the check on that understatement: a quarter of a gram of
gelatine protein per fish oil capsule, under a fifth of a gram of starch per
algae capsule. EPA, DHA and vitamin E are not tracked and stay out. Six fish
oil labels (dm, Rossmann, shop-apotheke) and three algae oil labels
(doppelherz.de with dm for the pack, dm, Rossmann); Nature Love, Biogena and
the other vegan labels state DHA and EPA only, never the oil mass, and are not
used.

