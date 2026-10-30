# Fast food chains

A chain file holds a chain's own published nutrition for its core menu, the
way `../cafe/starbucks-de.json` holds Starbucks Germany's: the maker's figures
per item, where they were published, the day they were retrieved and a
SHA-256, and nothing invented. Facts from a nutrition table are not
copyrightable; the attribution names the chain and the retrieval day as the
café catalogue's does.

## McDonald's Deutschland — `mcdonalds-de.json`, 30 October 2026

McDonald's Deutschland publishes no nutrition PDF. Each product page under
https://www.mcdonalds.com/de/de-de/product/ shows a *Nährwerte* table per
100 g and per portion with the portion weight, and the allergens; the page
reads that table from the site's own item data service, which the page names
as its `data-product-api-url`
(`/dnaapp/itemDetails?country=DE&language=de&showLiveData=true&item=<id>`).
The site's nutrition note
(https://www.mcdonalds.com/de/de-de/produkte/naehrwert-und-allergeninformationen.html)
says the values are rounded European averages from accredited laboratories for
standard recipes and portions, that recipes change and the website shows the
current state. The file records every row's product page, its data URL and the
SHA-256 of the response text, and a combined SHA-256 over the rows.

The 14 category pages (burger, McWrap, McCrispy, McNuggets & Fingerfood, veggie,
sides, breakfast, drinks, desserts, McCafé, McSmart snacks, Happy Meal, McMenü,
highlights) list 164 products. 114 are the core menu in the file: burgers,
chicken, wraps, fries, salads, sauces and dips, breakfast, desserts and McCafé
pastries, drinks in their sold sizes (0,5 l, 0,25 l, Grande, Small) and the
Happy Meal items. 50 are listed under `excluded` with the reason: promotional
products the site itself files under *Aktionsprodukte*, seasonal and
limited-time items (the 1955 and Fan Favorites burgers, McWings and the chicken
boxes, the flavoured McCafé drinks and Red Bull energizers of the season,
seasonal McPops, donuts and cookies, McFlurry Daim), campaign menus, add-ons
(McFlurry toppings, cream, oat drink, lactose-free milk) and two rows the site
marks *Do not Show*. A table states energy (kJ and kcal), fat, saturated fat,
carbohydrates, sugar, fibre, protein and salt and no micronutrient; salt is
converted to sodium as the café catalogue does (g × 400).

## Can chain items ship through the data pack without an app change?

Not correctly, so the builder stops before the bundle. What was studied:

- `Akari/CafeDrinkCatalog.json` is in the data pack's file list (format 1,
  `Scripts/build_food_data_pack.py`, `Akari/FoodDataFiles.swift`), and the
  app accepts a downloaded copy when it decodes with `version == 1` and unique
  ids (`CafeDrinkCatalog.decodes`). A record with an id such as
  `chain:mcdonalds-de:big-mac` would decode and be found by its name, under the
  branded group because it carries a brand.
- But the app treats every record of that file as a café drink:
  `CafeDrinkCatalog.swift` gives each record coffee or tea artwork from its
  `category` (anything that is not coffee becomes tea), the meal composer and
  the description service treat a matched record as a drink
  (`requestsDrink`, `FoodMealComposition`), the search applies the milk-word
  rules of lattes, and the kitchen measures read `measurementDensity` as a
  liquid. A Big Mac would show with a teacup and be handled as a drink.
- `Scripts/export_catalogue_health.py` also stops on a café record whose id is
  neither `generic` nor `starbucks-de`.

So `Scripts/build_chain_catalog.py` builds the records in the café record
shape, basis per 100 g with the published portion, into `build/ChainCatalog.json`
and does not add them to the bundled catalogue. The app change that would let
them ship: a record field the app honours for artwork and for the drink rules
(a `kind` such as `food`, with `category` mapped to the artwork taxonomy:
burger, fries, poultry, cookie, soft-drink, coffee), or a separate
`ChainCatalog.json` registered in `FoodDataFiles` with a pack format bump. Until
then the health board's *Fast food chains* collection counts the file's rows,
verified "all" as the maker's own figures, as the Starbucks collection does.

## Rebuild and tests

```
python3 Scripts/build_chain_catalog.py
python3 -m unittest Scripts.test_chain_catalog
```
