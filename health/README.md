# Catalogue health

`latest.json` holds the last passed data audit's numbers: catalogue coverage, the dishes and drinks beside the catalogue (recipes and how many are reviewed, global dishes, café drinks as generic recipes and Starbucks Germany sizes), typical portions and their web check, staples with each category's English and German name and food count, drinks, the photo, compose, parser and portion-picker scoreboards, the data lane's test count, `nutrients` (for fibre, sugar, saturated fat and the twelve micronutrients, the share of rows that declare an amount, overall and per national table) `collectionGroups` and `collections` (the dashboard's collection tiles, each in a group, with its names, Fluent sticker and count, `null` for one not built yet; a count is read from these numbers or counts the catalogue rows whose English name matches a pattern and not its optional `unless` pattern, which is approximate by design; `verified` is how many of the count are verified, that is curated references (`is_verified` in `Akari/ReferenceFoods.sqlite`, the hand-checked foods) or the maker's own published data: staples whose rows all are, recipes whose ingredients all are, the matched rows that are, all of the café chains (Starbucks Germany's published sizes, the only chain so far), the verified drinks and the supplements, and none of the generic café drinks yet; the lists are `COLLECTION_GROUPS` and `COLLECTIONS` at the top of the export script), `cuisines` (per cuisine, the global dishes that have a recipe, matched by their English name against the recipes' names and aliases, most first, then `PLANNED_CUISINES` with `null`; courses such as dessert or breakfast are left out), `cuisinesWithoutRecipe` and `missingRecipes` (how many global dishes with a cuisine have no recipe yet, and their English names). `history.jsonl` adds one compact line per audit, keyed by `auditFinishedAt`.

**Verified**

- **Identified:** the right food, not a lookalike
- **Localized:** English and German names
- **Findable:** the words people type bring it up
- **Portioned:** a typical serving, with a source where one exists
- **Complete:** calories, carbs, protein, fat and at least 8 of 12 vitamins and minerals
- **Sourced:** every value measured by a national institute, a gap filled only from a second one and marked

The dashboard's Collections card shows this checklist in English and German.

`Scripts/export_catalogue_health.py` writes both from the audit's own logs; `Scripts/run-data-audit.sh` runs it after the whole audit passed, so nothing here comes from a run that did not happen. Publishing ignores this folder in the audit stamp.
The admin dashboard's Foods page reads `latest.json` from https://raw.githubusercontent.com/hejrafa/AkariFoodIndex/main/health/latest.json; `history.jsonl` is kept for later charts and is not read by the dashboard yet.
