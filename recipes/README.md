# Akari recipe catalogue

Akari owns the definition of common dishes. A margherita is always Akari's
dough, passata, mozzarella, basil and olive oil in Akari's ratios, instead of
whatever the on-device model guesses each time. Each dish is a list of real
rows from the national composition tables Akari already bundles (BLS, USDA,
CoFID, Ciqual, MEXT) with a gram amount for one ordinary home serving.

`recipes.json` is the source: twenty hand-reviewed dishes (`"origin": "reviewed"`)
and about 1,500 generated ones (`"origin": "generated"`, see below).
`Scripts/build_recipe_catalog.py` turns it into `Akari/RecipeCatalog.json`,
which ships in the app bundle. It is not part of the Open Food Facts release
this repository builds; the weekly refresh never reads it.

## Estimate policy

- **Every number traces to a reference row.** Nutrition is never typed by hand.
  The serving's grams are the sum of its ingredients.
- **The café rule applies.** A dish declares a nutrient only when every
  ingredient declares it. Source energy is summed, not recomputed from macros.
  Nothing missing is filled with zero. This is why some ingredient choices
  prefer a row from another table: the BLS mozzarella and feta leave fibre
  undeclared, BLS rapeseed and sunflower oil leave water undeclared, and either
  would remove that value from the whole dish.
- **Ratios are Akari estimates.** They describe one ordinary home serving, not
  an analysed recipe or a restaurant portion. Cooking losses (water lost from
  dough while baking, for example) are not modelled, exactly as in the café
  catalogue. Every logged amount is marked as an estimate and stays editable.
- **The app logs the ingredients, not the dish total.** Choosing a recipe stages
  a dish whose ingredients are ordinary reference foods with gram amounts, so
  each one can be edited, swapped or removed like any other food.

## Generated recipes

Most dishes are drafted in a Claude Code session and accepted by scripts that
only validate; there is no API key and no network model anywhere.

1. `Scripts/list_recipe_candidates.py` writes `candidates.json`: the composite
   dishes of the national tables (BLS groups X and Y, Ciqual 25xxx, MEXT 18xxx,
   USDA FNDDS and CoFID rows whose names are dishes), each with its `tableRow`,
   plus `global-dishes.json`, a curated list of dishes the tables name poorly,
   deduplicated by normalised name. First pass: 1,981 candidates (curated 457,
   BLS 1,156, USDA 252, Ciqual 59, MEXT 50, CoFID 7).
2. `Scripts/draft_recipes.py --batch N` writes `drafts/batch-N.todo.json`, the
   next 100 candidates with the table row's energy and macro shares as a hint.
   The draft `drafts/batch-N.json` follows `drafts/README.md`: names in both
   languages, 2–12 generic ingredients with grams for one home serving, a
   serving label, aliases and artwork, or a `skip` with its reason.
3. `--resolve N` resolves every ingredient name through `ingredients.json` (a
   reviewed lexicon of about 470 recipe ingredients, each mapped to one row with
   English and German display names), Akari's verified references, or exactly
   one table row with that name. Ambiguous names get their candidate rows
   written next to them and resolve stops until a row is picked. A row needs
   an English name or a reviewed one; French and Japanese-only rows are refused.
4. `--accept N` moves resolved dishes into `recipes.json`. A dish with an
   ingredient that cannot be traced to a row goes to `unresolved.json`; a dish
   whose name already belongs to another recipe, a café drink, a known product
   or a plain generic food is recorded there as a duplicate. Aliases that
   collide are dropped. Reviewed entries are never touched. Every command is
   idempotent.
5. `Scripts/audit_recipes.py` writes `analysis/recipe-audit.json`: per dish the
   serving, energy per serving and per 100 g, and, where the candidate came from
   a table, that row's energy and the ratio. It flags energy ratios outside
   0.7–1.4, servings outside 120–900 g, fat or protein energy shares more than
   15 points from the table row, and dishes missing a core value (energy,
   macros, sugar, fibre, saturated fat, sodium, water). Flags never block the
   build; they are the review list.

First pass (1 October 2026), 20 batches: 1,539 dishes drafted and 442
candidates skipped by the drafter (single foods, sauces, dips, baby food,
duplicates). Accept added 1,476 dishes, set aside 60 more as duplicates of an
earlier dish, and left 3 unresolved for lack of a table row (tteokbokki, dolmades,
açaí bowl). The audit flags 188 of 1,496 dishes: 90 miss a core value (mostly
Japanese dishes, whose MEXT dashi, mirin, rice vinegar and noodle rows leave
sugar, saturated fat or fat undeclared), 69 differ from their table row's fat
share, 14 from its protein share, 23 have an energy ratio outside 0.7–1.4
(the table row is often a different preparation, such as BLS's sauce-only
Frankfurter Grüne Soße or USDA's filling-only sloppy joe), and 39 have a
serving outside 120–900 g (dumplings, small sandwiches, desserts, drinks).

Review (2 October 2026): dashi moved from mext:17021, which leaves fat
undeclared and so took fat off 17 Japanese dishes, to mext:17148, the same
bonito and kombu dashi with fat and fibre declared. Fat now shows on 15 of
them; sukiyaki, chikuzenni and nikujaga still lack it because shirataki
(mext:02005) has no row that declares fat. The audit now counts 61 fat-share
and 10 protein-share differences; the other counts are unchanged.

Second pass (2 October 2026): the last five dishes missing a macronutrient
each had one ingredient row without it. Shirataki now uses mext:02004, plain
konjac from the same table with fat declared (sukiyaki, chikuzenni,
nikujaga); tartiflette's Reblochon uses ciqual:12039, Munster, the closest
washed-rind cheese that declares carbohydrate, under the Reblochon name;
Christmas pudding's shredded suet uses BLS beef tallow (bls:Q890000) and its
candied lemon peel BLS candied orange peel (bls:R381100). No dish misses fat,
protein or carbohydrate now; the audit flags 187 dishes, 89 for a missing
core value and 58 for fat share.

## Adding a dish by hand

1. Look up the real rows first, for example
   `sqlite3 Akari/ReferenceFoods.sqlite "select id, name, alternate_name, nutrients_json from reference_food where name like '%Mozzarella%'"`.
   Use the right preparation: cooked pasta for a pasta dish, raw banana for a shake.
   Check which nutrients each row declares; one row without fibre removes
   fibre from the dish.
2. Add an entry to `recipes.json` with `"origin": "reviewed"`:
   - `id`: `akari:recipe:<slug>:v1`. Change the version when a change to the
     ingredients should not be confused with earlier logs.
   - `names`: English and German display names.
   - `aliases`: lowercase phrases people type or say in both languages,
     including common misspellings and compounds. A phrase may belong to only
     one dish and must not collide with a café drink or a known product. Avoid
     bare category words (`pizza`, `curry`) that name many dishes.
   - `artworkID`: an existing id from `Akari/FluentFoodArtwork.json`; use
     `plate` when nothing fits. Never add artwork.
   - `serving`: a label in both languages and a `count`. The count is what a
     spoken number counts: "two pancakes" with a serving of 3 pancakes is two
     thirds of a serving.
   - `ingredients`: `reference` and `grams`, in the order the dish should list
     them. `"role": "optional"` marks a garnish a reviewer may want to drop; it
     is still part of the default serving and its nutrition.
   - `notes`: one or two sentences on the ratio choices.
3. Run the build and the tests:

```
python3 Scripts/build_recipe_catalog.py
python3 -m unittest Scripts/test_recipe_catalog.py
```

A reference that does not exist, an unknown artwork id or a duplicated alias
fails the build. Running the build twice changes nothing.

## How the app uses it

`Akari/RecipeCatalog.swift` decodes the bundle once, off the main thread, when
food logging opens. A description such as
"half a pizza margherita" or "zwei Pfannkuchen" becomes the catalogue dish,
scaled by the spoken amount, before the model's suggested ingredients are
considered. A branded or restaurant name ("Dr. Oetker Pizza Margherita") keeps
its own match. Search lists a dish in the Generic group when the
query is one of its names or the start of one; a lone ingredient word
("egg", "Käse") lists only a dish of exactly that name. Choosing a dish
stages it with its ingredients, shown under the lexicon's reviewed names.
