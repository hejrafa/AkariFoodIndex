# Recipe drafts

Each `batch-N.todo.json` lists up to 100 candidate dishes from `../candidates.json`.
Its `batch-N.json` is the draft written for it in a Claude Code session (no API,
no network model). `Scripts/draft_recipes.py --resolve N` then writes the
reference row it found next to every ingredient (`resolved`), or the candidate
rows (`candidates`) when the name is ambiguous. `--accept N` moves the finished
dishes into `../recipes.json` with `"origin": "generated"`.

## Draft format

```json
{
 "batch": 1,
 "drafted": "2026-10-01",
 "drafter": "Claude in the Akari Claude Code session",
 "dishes": [
  {
   "key": "spaghetti carbonara",
   "names": {"en": "Spaghetti carbonara", "de": "Spaghetti Carbonara"},
   "serving": {"label": {"en": "1 plate", "de": "1 Teller"}, "count": 1},
   "artworkID": "pasta",
   "aliases": {"en": ["carbonara", "pasta carbonara", "spagetti carbonara"],
               "de": ["carbonara", "nudeln carbonara", "spaghetti alla carbonara"]},
   "ingredients": [
    {"name": "cooked spaghetti", "grams": 220},
    {"name": "bacon, cooked", "grams": 40},
    {"name": "egg", "grams": 50},
    {"name": "parmesan", "grams": 20}
   ]
  },
  {"key": "apfelmus", "skip": "a single food, not a dish"}
 ]
}
```

## Rules for drafting

- `key` is copied from the todo entry. Every todo entry gets a dish or a `skip`.
- **Names**: a clean English and German display name, as a menu or a person
  would write it. Translate French (`fr`) and Japanese (`ja`) table names.
- **Ingredients**: 2 to 12, generic foods only, no brands, nothing invented. Prefer
  the exact names of the vocabulary that `--batch` prints (`../ingredients.json`).
  Otherwise use the plain name a national food table would use ("lamb, roasted").
  Use the weight as eaten in the dish: cooked pasta, rice and meat for
  cooked components, raw for raw ones. A table dish component such as
  "bolognese sauce", "tomato sauce", "pizza dough" or "gravy" may be one ingredient.
- **Grams**: one ordinary home serving. Mains are usually 300–650 g, sides
  and starters 120–300 g, desserts 100–250 g, drinks 200–400 g (grams ≈ ml).
  Leave out salt, pepper and dried herbs under 2 g: they add nothing, and their
  rows can drop nutrients from the whole dish.
- **Serving**: a label in both languages ("1 plate"/"1 Teller", "2 slices"/"2 Scheiben").
  `count` is how many pieces the label counts ("3 pancakes" is 3); otherwise 1.
- **Aliases**: 3 to 8 per language, lowercase. Other names, word orders,
  compounds and likely misspellings ("spagetti carbonara", "currywurst mit pommes"
  is a different dish, so not that). Never a bare category ("pizza", "curry",
  "soup", "salad", "sandwich", "cake") or a single ingredient ("chicken").
- **Artwork**: an id from the list `--batch` prints, or `"neutral"`.
- **Skip** a candidate that is not a dish someone logs as one: a single food
  or a cooking-method variant of one ("pork chop, fried"), a sauce, dip or
  dough on its own, a preserve, a baby food, an alcoholic cocktail (logged
  per drink elsewhere), or a duplicate of another candidate in the batch.
- The `hint` of a table candidate is that row's energy per 100 g and its
  protein, fat and carbohydrate energy shares. A draft far from it is either a
  different dish or wrong ratios; the audit compares them after the build.
