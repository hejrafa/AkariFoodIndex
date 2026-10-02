# Typical portions

How much of a generic food an ordinary person logs when they say nothing about
the amount: the natural unit (`piece`, `slice`, `glass`, `portion`,
`tablespoon`, …), its weight (or volume for drinks) and the usual count for
one eating occasion. 1 banana, 2 slices of bread, 1 glass of milk (250 ml),
1 portion of cooked rice (180 g).

`typical-portions.json` is synced into the app as `Akari/FoodTypicalPortions.json`
(`Scripts/sync_food_index_data.py`). The app uses it only for generic reference
foods, after its existing special cases (per-serving labels, cooking oil, bread
slices, reviewed source fixes) and before falling back to a source's first
measure or 100 g. A source single item in another unit keeps the source, a
branded product keeps its label's serving, and the person's own last amount
replaces the typical one afterwards.

## Sources

- **Weights** come from the reference row's own household measure whenever
  one matches the unit (`"source": {"kind": "household-measure", …}` with the
  row and its label). Otherwise the drafted weight ships as
  `"kind": "estimate"` with a one-line reason. A drafted weight more than 40 %
  away from a matching source measure goes to `unresolved.json` instead.
- **Typical counts** are always Akari estimates (`"typicalSource": "estimate"`).

## Pipeline

1. `python3 Scripts/draft_typical_portions.py --todo` writes `todo.json`: every
   group of `serving-identities.json`, every ingredient of the recipe catalogue
   and the generic names of `GenericFoodSearchAliases.json` and
   `AkariTests/SearchExamples.json`, merged into one identity when they share a
   name, each with its reference rows and their household measures.
2. `--batch N` writes `drafts/batch-N.todo.json`; the draft `drafts/batch-N.json`
   is written in a Claude Code session following `drafts/README.md` (no API,
   no network model).
3. `--accept` rebuilds `typical-portions.json` and `unresolved.json` from all
   drafts. It is idempotent and never overwrites an entry with
   `"origin": "reviewed"`.

The app matches a product by reference row first, then by name: the row's
name with word order ignored and "raw"/"fresh" dropped must equal one of the
identity's names ("Banana raw" is "banana", "Rice boiled" is "boiled rice").

First pass (1 October 2026), 6 batches: 878 identities, 837 portions (78 with a
source household measure, 759 estimates), 40 skipped as never logged on their
own (stocks, raw doughs, leavening, thickeners), 1 unresolved (corn taco
shell: the USDA "1 medium" shell is 28 g against a drafted 12 g).
