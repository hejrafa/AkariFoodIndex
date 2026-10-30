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

## How chain items reach the app

`Scripts/build_chain_catalog.py` builds the records into `Akari/ChainCatalog.json`
(version 1), a data pack file of its own beside `CafeDrinkCatalog.json`, in the café
record shape plus two fields the app honours:

- `kind`: `food` or `drink`, from the item's category, so a Big Mac is a food and
  never meets the café drink rules (milk words, liquid measures, a teacup);
- `artwork`: the asset the app already draws for it (`Akari/FluentFoodArtwork.json`),
  from the category with a few name overrides, both tables in the script:

| category | kind | artwork | by name |
| --- | --- | --- | --- |
| burger | food | burger | |
| chicken | food | poultry | McChicken, McCrispy: burger |
| wrap | food | burrito | |
| fries | food | fries | |
| salad | food | salad | |
| sauce | food | jar | |
| breakfast | food | sandwich | croissant; pancakes, McGriddles: pancakes; McWrap: burrito |
| dessert | food | ice-cream | cookie; cheesecake, cake, brownie: cake; muffin: cupcake; donut, McPops: doughnut; Apfeltasche: pie; Apfeltüte, Fruchtquatsch: apple; McFreezy: shaved-ice |
| coffee | drink | coffee | tea, green tea, matcha: tea |
| drink | drink | soft-drink | water; orange juice, Schorle, Capri-Sun: juice; milkshakes: milk |

The item's name is the chain's own in both languages (`names`), and the builder adds
what people call it beside that: a count read either side ("McNuggets 6er") and the
fries by size ("Pommes mittel", "medium fries"). A food is one item at its published
weight; a drink whose name states its size ("0,5l", "250 ml") is measured by volume at
that size, and one that states none ("Café Grande", "Mezzo Mix") is one serving at its
published weight.

In the app, `ChainCatalog` loads the file through `FoodDataFiles`; its records are
café-sourced products, found by name and chain ("Big Mac", "McNuggets 6er",
"McDonald's Big Mac"), and a description that names an item outright ("1 Big Mac") is
the chain's item ahead of a national table's row of the same name. The nutrition is the
chain's as published: energy, macros and sodium from salt, no micronutrients, with no
verified mark, as Starbucks' records.

Adding the file is data pack format 2 (`Scripts/build_food_data_pack.py`); the published
pack stays format 1 (`PUBLISHED_FORMAT`) until an app of format 2 is on TestFlight, so
apps already out keep receiving packs.

## Rebuild and tests

```
python3 Scripts/build_chain_catalog.py
python3 -m unittest Scripts.test_chain_catalog
```
