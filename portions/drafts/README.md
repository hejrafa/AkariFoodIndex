# Typical portion drafts

`batch-N.todo.json` lists up to 150 food identities from `../todo.json`: the
names that mean the same food (English and German, normalised), the reference
rows the identity applies to, and the household measures those rows carry.
`batch-N.json` is the draft written for it in a Claude Code session (no API, no
network model). `Scripts/draft_typical_portions.py --accept` builds
`../typical-portions.json` from all drafts.

## Draft format

```json
{
 "batch": 1,
 "drafted": "2026-10-01",
 "drafter": "Claude in the Akari Claude Code session",
 "entries": [
  {"key": "banane", "unit": "banana", "gramsPerUnit": 120, "typical": 1,
   "reason": "edible weight of a medium banana"},
  {"key": "milch", "unit": "glass", "milliliters": 250, "typical": 1,
   "reason": "a regular drinking glass"},
  {"key": "reis", "unit": "portion", "gramsPerUnit": 180, "typical": 1,
   "reason": "cooked rice as a side", "excludeReferences": ["bls:C352000"]},
  {"key": "tonkatsu sauce", "skip": "a condiment only used inside dishes"}
 ]
}
```

## Rules

- One entry per todo identity, in todo order: a portion or a `skip` with a reason.
- **unit** is the natural way people count this food, a `FoodQuantityUnit`:
  `piece`, `slice`, `banana`, `egg`, `cookie`, `bar`, `glass`, `cup`, `bottle`,
  `can`, `tablespoon`, `teaspoon`, `portion` (an amorphous helping: rice, pasta,
  stew, salad, minced meat). Whole fruit and vegetables are `piece` (banana is
  `banana`, egg is `egg`); bread and cheese are `slice`; drinks are `glass`;
  oils, sauces, dressings and spreads are `tablespoon`; spices and sugar are
  `teaspoon`.
- **gramsPerUnit** is the edible weight of one unit as the food is listed
  (cooked for a cooked row). For drinks and other liquids write
  **milliliters** per unit instead.
- **typical** is how many units an ordinary person eats or drinks on one
  occasion when they say nothing about the amount: 1 banana, 2 slices of
  bread, 1 glass of milk, 1 portion of rice, 2 slices of cheese,
  1 tablespoon of oil. Fractions are fine (0.5 avocado).
- If the identity's household measures already contain your unit, use that
  measure's weight unless it is clearly a different size; accept replaces
  your weight with the source's anyway and sets the entry aside when the two
  are more than 40 % apart.
- **excludeReferences**: rows listed under the identity that are a different
  preparation from your portion (raw rice under a cooked-rice identity, dried
  under fresh). They then keep their old default.
- **skip** an identity that nobody logs on its own (a minor dish component
  such as dashi, a thickener, baking powder), that is not one food (a mixed
  category), or whose rows are clearly unrelated.
- **reason**: one short phrase on where the weight comes from (a typical
  medium item, a standard glass, a common serving).
