# Nutrient fills

A verified food's missing micronutrient is filled from a second national
table's row for the same food in the same state. The value is copied as that
institute measured it, per 100 g as the reference index stores it, and marked
with the row it came from. A fill is never averaged, never guessed and never
overwrites a value the food's own table declares. This replaces the earlier
principle that nothing missing is filled.

## The file

`fills.json` holds every reviewed fill:

```text
{
  "version": 1,
  "policy": "second-table-fills-v1",
  "fills": [
    {"id": "<target row id>", "nutrient": "selenium", "value": <per 100 g>,
     "from": "<source row id>", "reviewed": "<YYYY-MM-DD>", "note": "<optional>"}
  ]
}
```

`id` is the verified target row, `nutrient` one of the twelve micronutrients of
`Scripts/build_reference_food_index.py`, `value` the source row's measured
value per 100 g in the index's unit, `from` the source row, `reviewed` the day
the fill was reviewed and `note` an optional remark.

## Review

`Scripts/list_nutrient_gaps.py` lists every micronutrient a verified food does
not declare, with the rows of the other national tables that declare it, into
`build/nutrient-gaps.json`. A row is a counterpart when it shares the food's
normalised English or German display name, or when the words of its English
name match: the same state words (raw, cooked, fried, dried, canned, smoked
and the like, read from the display name and the table's own names, a name
with none being the raw food), the other words the same but for at most one
grade word under rule (d), the same food class
(`FoodIndex/classify_artwork.py`), and no brand or "with …". It reads the
index only, never the network.

A fill is accepted only when the counterpart is the same food in the same
state: by name, and by macro plausibility, with calories within 15 % and
protein, fat and carbohydrates each within 3 g per 100 g of the target row.
A counterpart that fails either test is skipped with its reason. A value the
counterpart itself has from a fill is never copied on. Every accepted fill is
also read: a counterpart whose words match but which is another food (daikon
sprouts for the root, a potato croquette for fried potatoes) is dropped, and
so is a value far outside every other measured value of the same food in the
index, which is a source error.

## Review rules

Every batch applies these on top of the name and macro tests:

- **(a) No US selenium for European grain, meat or eggs.** A USDA row never
  gives selenium to a cereal, bread, bakery, meat, offal, sausage or egg food of a
  European table: US soils and feed give several times the European
  selenium. USDA stays a source for dairy, fish, fruit, vegetables, oils and
  drinks.
- **(b) Disagreeing counterparts mean no fill.** When the plausible
  counterparts' values for the nutrient lie more than tenfold apart and more
  than 5 µg per 100 g apart, the gap stays open.
- **(c) The nearest table first.** With several plausible counterparts, a
  European table (CoFID, Ciqual, BLS) comes first, then MEXT, then USDA, then
  the one whose macros lie closest. The fill's `note` names the alternatives.
- **(d) A word match differs by a grade, cut or variety word only.** A
  counterpart found by the words of its name is offered only when the one
  word it adds or drops is a grade of the same food (unspecified, fresh,
  whole, peeled, drained, skinless, lean, extra, shelled, unsalted, UHT,
  pasteurised, stick, bar, bottled, chilled, homemade, refined, cold, plain,
  fat, free, low, hard, soft, baby, new, type, pitted, stalk, floret, groat,
  wild, farmed), a cut or part of the same animal (topside, flank, spare,
  leg, loin, thigh, breast) or a variety of the same species (iceberg,
  romaine, leaf, cherry, basmati, Alaska, Arctic, Scotch, Roquefort, icing,
  mixed, coarse). A species, grain, flavour, filling or product word names
  another food, and so does a colour word, since red cabbage is not cabbage
  and brown shrimp not shrimp; such a pair is not offered, and what this
  drops (Tomato, red; Peas for green peas) stays open, with no exception
  list. A fortified row is never offered; by review it may give a mineral,
  which fortification does not add, with a note saying so. A peeled,
  skinless or drained counterpart gives minerals only, since peel, skin and
  canning liquid carry the vitamins.
- **(e) No iodine across borders where salt or feed brings it.** Bread and
  bakery, sausages and cured meat, dairy and eggs take no iodine from another
  table: their iodine comes from the iodised salt a baker or butcher uses and
  from the iodine in cattle and hen feed, and both differ from country to
  country. Fresh meat and offal, fish and seafood, fruit, vegetables, grains,
  nuts, oils, sugars and drinks may take it.

## The build

`Scripts/build_reference_food_index.py` reads `fills.json` and stops on a fill
whose target is not a verified food, whose source row is missing or comes from
the target's own table or from no national table, whose value is not the
source's finite measured value, or whose target already declares the nutrient.
It writes the value into `nutrients_json` and the source into
`nutrient_fills_json` (`{nutrient: source row id}`), and records
`nutrient_fills_policy` and `nutrient_fill_count` in the index's metadata.

A fill changes neither which foods are verified nor the 8-of-12 rule: only an
already verified food takes one, and verification reads the row's own
declared values. So the verification policy stays
`curated-reference-foods-v7` and the data pack stays format 1. An app of
format 1 reads named columns of `reference_food`, never `nutrient_fills_json`,
and accepts the index by its application id, schema 6 and policy, which the
fills leave as they are.
`Scripts/test_reference_foods.py` holds the bundled index to these rules.
