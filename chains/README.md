# Chains

A chain file holds a chain's own published nutrition for its core menu, the
way `../cafe/starbucks-de.json` holds Starbucks Germany's: the maker's figures
per item, where they were published, the day they were retrieved and a
SHA-256, and nothing invented. Facts from a nutrition table are not
copyrightable; the attribution names the chain and the retrieval day as the
café catalogue's does. Its top-level `kind` says which of the admin board's
collections it belongs to: `fast-food`, `restaurant` or `bakery`.

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

## Burger King Deutschland — `burgerking-de.json`, 30 October 2026

Burger King Deutschland's *Nährwerte & Allergene* page
(https://www.burgerking.de/naehrwerte_allergene) has no table: it sends readers to each
product under *Menü*, whose *Lebensmittelinformationen inkl. Allergenen und Nährwerte*
shows the values per 100 g/100 ml and per portion with the portion size, and the
allergens. The page says the values come from the suppliers' food analyses and apply to
Germany only. The site is a JavaScript app; the menu and product pages read everything
from the chain's own content service, Sanity dataset `prod_bk_de` at
`czqk28jt.apicdn.sanity.io` (per product the GraphQL operation `GetItem`). The file
records each row's product page, the service's public query for that item
(`data/query/prod_bk_de?query=*[_id=="<id>"]…`) and the SHA-256 of its result as compact
JSON with sorted keys, since the response carries a timing field; the combined SHA-256
covers the rows. The service also states fibre, which the page's table leaves out; the
file keeps it as the chain's own figure.

The menu's ten sections (Neu & Limitiert, Plant-based, Beef, Chicken, King Jr. Meal,
Snacks, Dips & Dressings, Drinks, Desserts, Frühstück) and their size pickers lead to 197
items. 142 are the core menu: burgers and their plant-based twins, tortillas, nuggets,
tenders and wings in their counts, fries, onion rings and cheese snacks, salads, dips and
dressings, breakfast, desserts and the King Shakes, Coca-Cola, Fanta, Sprite, Fuze Tea and
Lift in 0,25, 0,4 and 0,5 l, Monster, Vio and the coffees. 55 are under `excluded` with
the reason: 28 the site files under *Neu & Limitiert* (the Indian line, King's Steakhouse,
King's Cheesy Bacon, the King des Monats burgers, Hello Kitty and Ultimate King menus,
Curly and Cheesy BBQ Fries) and 3 more of the Indian line filed elsewhere, 3 summer items
(the Tropical Mango float and shake, King Fusion Smarties Erdbeere), 10 delivery-only
retail products (*BK Lieferservice* bottles and Ben & Jerry's tubs), Heineken (alcoholic),
the second, unnamed Caffè Crema size, 8 items whose data states no values (Latte
Macchiato, Iced Coffee Caramel, King Shake Espresso, Hohes C, the double Long Chicken and
Crispy Chicken, 3er Flame Wings) and Hot Brownie mit Eis, whose per-100 g and per-portion
energy contradict each other with no way to tell which is right.

Where the service leaves a per-100 value empty, it is derived from the portion and its
stated weight. Where a stated per-100 value contradicts the portion's own figure, kJ
against kcal decides energy and the energy decides fat, carbohydrate and protein; a fibre
or sugar contradiction no check settles leaves that nutrient out. Every such row says so in
`valueNotes` (Sprite 0,4 l, Fuze Tea, 6er Chili Cheese Nuggets, the Plant-based Double
Cheeseburger, Hot Brownie, Fries Chili Cheese Style). For the soft drinks the portion
figure is the sold volume and the per-100 column is per 100 ml; such a row gives
`servingUnit` `ml`. The King Shakes' volumes (0,25, 0,4 and 0,5 l for Small, Medium and
Large) are stated in their descriptions, recorded as `volumeSource` `description`.

## Subway Deutschland — `subway-de.json`, 30 October 2026

Subway Germany's *Allergene und Nährwerte* page
(https://www.subway.com/de-DE/MenuNutrition/Nutrition) links the nutrition as a PDF,
"Germany Nutritional Information Full Menu C4 2026" (three pages, made from an Excel sheet
on 7 August 2026 and headed *Nährwertinformationen September 2026, Deutschland*), which
the file records with its address and SHA-256; every row names the PDF page it stands on.
The sheet states per portion, with the portion weight, and per 100 g: energy in kJ and
kcal, fat, saturated fat, carbohydrate, sugar, fibre, protein and salt. Its values include
the recommended bread or wrap, the chosen protein, the standard vegetables and sauce; a
sub is the 15 cm one, and the sheet says to double the values for a Footlong (salads
excepted), so a Footlong is two subs and has no row of its own.

160 lines lead to 106 core rows: 16 subs, 15 wraps and 14 salads named by their filling
("Italian B.M.T. Sub", "Tuna Wrap", "Ham Salat"), the five *Unsere Kreationen* subs,
19 baked potatoes, three panini, two Footlong dippers, ten sides (waffle fries, nacho
chicken bites, cheese bites, coleslaw, crisps), four drinks, ten sauces and eight cookies. A sub is found by its
filling alone, with or without "Sub" and "15 cm", and without the dots of its name
("Italian BMT"); a wrap, salad or baked potato by its filling and its kind. 54 are under
`excluded`: the 41 components for building one's own sub (breads, cheeses, toppings and
single fillings), seven drinks whose sugar the sheet prints under fat and saturated fat
with no carbohydrate (Pepsi, Schwip Schwap and its Zero, 7UP Zero, Mountain Dew, Lipton
Eistee Peach, Capri-Sun), Lipton Eistee Lemon, whose per-100 column is shifted the same
way, five rows whose figures contradict themselves (the Spicy Vegan Patty salad and the
BuddyFruits mousse, whose energy does not fit their macronutrients, the balsamic vinegar
with 28 kcal and no macronutrients, and the garlic and herb sauce, whose two columns state
22 and 570 kcal) and the seasonal pumpkin spice cookie. The Beef Chili salad keeps its
values without its 36 g of fibre, which breaks its energy, and the Brookie Cookie Cup
without its 24 g of salt per 100 g; both say so in `valueNotes`, as Burger King's rows do,
under the same rules.

## KFC Deutschland — `kfc-de.json`, 30 October 2026

KFC Deutschland's FAQ links "Nährwert- und Allergeninformationen" to
https://static.kfc.de/pdf/ALLERGENE.pdf, 33 pages: *Zusatzinformationen zu verpackten
Produkten* and *zu zubereiteten Produkten* (September 2026) and *zu Kwench Produkten*
(July 2026). The server stalls scripted downloads, so the file was saved from a browser on
30 October 2026; it is recorded with its SHA-256 and every row names its page. Each page
holds two columns of product blocks, read one half-page at a time. A prepared product
states its portion size and per 100 g (per 100 ml for drinks) and per portion: energy in
kJ and kcal, fat, saturated fat, carbohydrate, sugar, protein and salt. A packaged product
states its net quantity and per 100 g only: one stated in grams is that portion, a bottle
its volume, and a sauce stated in ml has no weight and stays per 100 g. Kwench drinks are
stated without ice; figures written "<0,1" are left out.

155 rows: the Original Chicken pieces, Hot Wings (upper and lower wing), Bites, Crispys,
Zinger and Original Chicken, the burgers ("Zinger" names the Classic Zinger Burger),
Twisters, sandwiches and the flatbread, fries, sides, salads, dips and dressings, sundaes
and cookies, the milkshakes, the hot drinks, the fountain drinks in 0,3, 0,4 and 0,5 l,
the bottles, and the Kwench iced lattes, shakes, refreshers and lemonades. 9 are under
`excluded`: four extras (bacon and cheese slices, butter, banana sprinkles), the fountain
Coca-Cola in its three sizes, whose 21 g of carbohydrate per 100 ml cannot make its 42
kcal, and the KitKat milkshakes, whose two energy columns contradict each other.

## Five Guys Deutschland — `fiveguys-de.json`, 30 October 2026

Five Guys Deutschland publishes one PDF,
https://www.fiveguys.de/wp-content/uploads/sites/33/2026/06/Allergen-and-Nutrition-Info.pdf
(four pages, 15 June 2026): an allergen table, a table of raw materials valid in Germany,
and on pages 3 and 4 *Nährwertangaben – Five Guys Deutschland*, per portion and per 100 g
(energy in kJ and kcal, fat, saturated fat, carbohydrate, sugar, fibre, protein, salt) with
no portion weight. The sheet gives a burger, a hot dog and a shake as their parts (patty,
bun, bacon, toppings, sauces, mix-ins), which are under `excluded` with the Currywurst Style
Loaded Fries, whose line the PDF breaks with one figure too many. The 15 rows are the
complete items people order: Mini, Little, Regular and Large Fries, Curry Style, Loaded and
Loaded Cajun Fries, the Veggie Sandwich and its cheese version, Grilled Cheese, the BLT, the
plain Milchshake and Milchshake Klein, the free peanuts and the burger in a lettuce wrap.
With no stated weight, 13 are one serving of their per-portion figures. The peanuts are per
100 g, the only column the sheet gives them, and so is the lettuce-wrap burger, whose
per-portion protein (2.4 g) breaks its energy while its per-100 g column fits; its row says
so.

## Nordsee Deutschland — `nordsee-de.json`, 30 October 2026 (restaurant)

Nordsee's product pages (https://www.nordsee.com/de/produkte, categories Highlights,
Snacks, Tellergerichte, Salate, Getränke, Desserts, Vegetarisch / Vegan and Supermarkt)
each show *Nährwerte* per 100 g (energy in kcal and kJ, protein, carbohydrate, sugar, fat,
saturated fat, salt) and the allergens, and no page states a portion weight, so every item
is per 100 g and opens at 100 g. The category pages embed the products and their values as
page data (`dati_pagina`); every product page was read as well and shows the same values.
Each row records its product page and the SHA-256 of that page as retrieved.

77 products: 41 are the menu, the burgers, wraps, the bagel, baguettes and Bremer rolls,
the fish boxes, Fish & Chips and Shrimps & Chips, the hot Backfisch, chips and potato box,
the plates (fish fillets, salmon, plaice, the salmon pasta and the fish soup, which states
no protein), the salads in their tortilla bowl and the two desserts. "Backfisch" alone
names the Heißer Backfisch XXL. 36 are under `excluded`: the 20 Supermarkt products (retail
packs) and 16 whose page states no values (the soft drinks, energy drinks, iced teas and
waters, the coffees and the Kids Burger Menü). Fish & Chips' kJ figure, which disagrees
with its kcal figure, is left out and noted.

## dean&david — `deananddavid-de.json`, 30 October 2026 (restaurant)

dean&david publishes *Nährwerte dean&david, Stand: September 2026* as a four-page PDF,
https://deananddavid.com/wp-content/uploads/2026/09/2026-09-dd-Naehrwertuebersicht.pdf
(made on 18 September 2026), recorded with its address and SHA-256. It states per
100 g/ml and per portion: energy in kJ and kcal, fat, saturated fat, carbohydrate, sugar,
protein and salt, no fibre, and no portion weight except the smoothies' 0,4 l and the
lemonade's 0,3 l. An item without a stated weight is one serving of its per-portion
figures, which must fit their own energy; a smoothie or the lemonade is its stated volume.
Salads are without dressing and bread, as the sheet says; bowls include their base and
sauce.

94 rows: 11 salads, five dressings, the slice of bread, 15 bowls (warm, cold and the two
kids' plates), eight sauces and dips, eight curries with rice, five sandwiches, five wraps,
three flatbreads, five sweets, two smoothies, the lemonade and 25 coffees, matcha drinks
and iced coffees, each with milk or oat drink as the sheet lists them. "Cappuccino mit
Milch" alone stays the café drink (see below); "dean&david Cappuccino mit Milch" is the
chain's. 76 are under `excluded`: 41 components for mixing one's own salad or bowl, 14 of
the autumn pumpkin spice line, 10 specials sold only in participating stores, seven
catering curries and wraps, two add-ons, the bar's Crodino Spritz (the sheet does not say
whether it is the alcohol-free one) and the Mango Passion smoothie, whose two energy
columns contradict each other.

## Hans im Glück — `hansimglueck-de.json`, 30 October 2026 (restaurant)

Hans im Glück's online menu, https://menu.hansimglueck-burgergrill.de/ (the chain-wide
menu with no restaurant chosen, recorded with its SHA-256), links every item to a page
whose *Nährwert & Allergene* view states the whole item ("Gesamt") as the kitchen makes it:
energy in kcal and kJ, fat, saturated fat, protein, carbohydrate, sugar and salt, with no
weight. The pages are rendered on the server; each row records its page and the page's
SHA-256. An item is one serving of those figures; a drink whose name states its volume
("Coca-Cola 0,33 l", "Durstlöscher Mango-Minze 0,5l") is that volume, its per-100 ml
values derived from the per-portion values and the stated volume. A burger's figures are
for the bun the house uses unless another is chosen.

189 items: 153 rows, the 39 burgers (beef, chicken, vegetarian, vegan, smash and the two
kids' burgers), eight salads, four bowls, the fries, sweet potatoes, loaded fries, sides
and dips, the fingerfood, the desserts and Froozys, the hot drinks, the Durstlöscher,
iced teas, still lemonades, soft drinks and waters in their sizes, and the alcohol-free
aperitifs and cocktails. The two ice creams and the vegan nuggets, listed on both the main
and the kids' menu, are one row each. 33 are under `excluded`: the 29 drinks with alcohol
and four combinations of items listed on their own (three desserts with a hot drink and
the kids' menu).

## BackWerk — `backwerk-de.json`, 30 October 2026 (bakery)

BackWerk's range, https://www.back-werk.de/de/sortiment (filters Belegte Brötchen,
Backwaren, Heiße Snacks, Süßes Gebäck and Getränke; the page loads more products as it
scrolls, 77 in all), links each product to a page whose *Nährwertangaben* tab states its
values per 100 g, or per 100 ml for the hot drinks: energy in kcal and kJ, carbohydrate,
sugar, fat, saturated fat, protein and salt, with the allergens. No page states a piece
weight, so an item is per 100 g (or 100 ml, `per100Unit` `ml`, basis `per100Milliliters`)
and opens at that amount. The values are the page's own data, rendered on the server; each
row records its page and the page's SHA-256.

52 rows: 15 filled rolls and baguettes, 12 hot snacks (hot sandwiches, börek, pizza, the
hot dog, poultry rolls), seven breads, pretzels and the croissant, 12 sweet pastries and six
hot drinks; Kaffee Schwarz states only energy and carbohydrate. 25 are under `excluded`:
the 23 bottled drinks and the tea, whose pages state no values, and the Börekstange
Hähnchenkebab, whose 287 g of carbohydrate per 100 g cannot fit its 286 kcal. The kJ
figures of the Börek Käse and the Chicken Kebab hot sandwich, which disagree with their
kcal, are left out and noted.

## Greggs — `greggs-uk.json`, 30 October 2026 (bakery, UK)

Greggs' nutrition page (https://www.greggs.com/nutrition) links its *Nutritional Information
(Guide only)* PDF, "correct at time of print (September 2026)", five pages made from an
Excel sheet on 10 September 2026, recorded with its address and SHA-256. Per product it
states the portion size (g/ml) and, per 100 g and per portion, energy in kJ and kcal, fat,
saturates, carbohydrate, sugars, fibre, protein and salt. A drink's portion is its volume
and its per-100 column per 100 ml; its row gives `servingUnit` `ml`. A bottle whose name sells
its size (the orange juices of 250 and 500 ml, the waters of 500 and 750 ml) is that bottle,
per 100 ml as stated, while the sheet's portion for it is a poured serving (150 or 100 ml);
its row says so. The brand is "Greggs ·
UK", so its notes say "in the UK".

271 products: 222 rows, the sausage rolls, bakes, pies and pasties, breakfast rolls and
baguettes, porridge, sandwiches, baguettes, oval bites, toasties and stotties, salads and
pasta pots, pizza slices, sweet bakes, doughnuts and the Yum Yum, biscuits and cookies,
dips, coffees, teas, iced drinks, lemonades, juices and water. "Sausage Roll(s)" is the
Sausage Roll, with "Sausage Rolls" as an alias. 49 are under `excluded`: 23 multipacks,
pizza boxes and meal boxes of items listed on their own, 11 extras added to another item
(syrups, shots, bacon, the spread), the ten items of the autumn pumpkin spice and bonfire
night lines, and five sold only in hospital shops. The two columns never contradict each
other.

## Bakery chains left out

- **Ditsch** (https://ditsch.com/de/b2c/shops/produktwelt; the old ditsch.de address
  answers 403): none of the 27 product pages states nutrition, only allergens, and the
  60-page product catalogue PDF (February 2026) carries none either.
- **Kamps, Le Crobag, Yorma's, Dunkin' Deutschland, Backfactory, Junge**: no per-product
  nutrition published (checked 30 October 2026).
- **Pret A Manger UK** was not needed: BackWerk and Greggs give the bakery collection
  well over 50 items.

## How chain items reach the app

`Scripts/build_chain_catalog.py` builds the records into `Akari/ChainCatalog.json`
(version 1), a data pack file of its own beside `CafeDrinkCatalog.json`, in the café
record shape plus the chain file's kind as `chainKind` and two fields the app honours:

- `kind`: `food` or `drink`, from the item's category, so a Big Mac is a food and
  never meets the café drink rules (milk words, liquid measures, a teacup);
- `artwork`: the asset the app already draws for it (`Akari/FluentFoodArtwork.json`),
  from the category with a few name overrides, both tables in the script:

| category | kind | artwork | by name |
| --- | --- | --- | --- |
| burger | food | burger | |
| chicken | food | poultry | McChicken, McCrispy: burger |
| wrap | food | burrito | |
| fries | food | fries | onion rings: onion |
| salad | food | salad | |
| sauce | food | jar | |
| sandwich | food | sandwich | dippers, baguettes: baguette; bagel: bagel; flatbread: flatbread |
| potato | food | potato | |
| bowl | food | rice | falafel plate: falafel |
| curry | food | curry | |
| bread | food | bread | |
| bakery | food | bread | pretzels: pretzel; croissant: croissant; simit: bagel; sausage rolls, bakes, pies, pasties: pie |
| fish | food | fish | prawns (Garnelen), shrimps: fried-shrimp |
| pasta | food | pasta | |
| soup | food | soup | |
| breakfast | food | sandwich | porridge: cereal; hash brown: potato; croissant; pancakes, McGriddles: pancakes; McWrap, tortilla: burrito; Breakfast King: burger |
| dessert | food | ice-cream | cookie; cheesecake, cake, brownie, blondie, tiramisu: cake; Rote Grütze: cherries; croissant, pain au chocolat: croissant; swirl, porridge bread, Franzbrötchen, Schoggibrötchen: bread; Körbchen, Apfelecke, Vanillestange: pie; muffin: cupcake; donut, doughnut, Yum Yum, McPops, churros: doughnut; biscuit, shortbread, gingerbread, flapjack, caramel crispy: cookie; éclair, iced finger, slice, bun: cake; Apfeltasche: pie; Apfeltüte, Fruchtquatsch, Quetschie, Fruchtmousse: apple; McFreezy: shaved-ice |
| snack | food | takeout | cauliflower wings: broccoli; crisps, chips: potato; fruit pot: apple; egg pot: egg; corn on the cob: corn; Doritos: corn; cheese, cheddar, mozzarella: cheese; peanuts: peanuts; pizza: pizza; hot dog: hot-dog; hot sandwich: sandwich; börek, rolls, savoury snacks: stuffed-flatbread |
| coffee | drink | coffee | Tee, Tees, tea, green tea, mint tea, matcha: tea |
| drink | drink | soft-drink | Wasser, water, Vio, Adelholzener, mineral: water; Eistee: tea; juice, orange juice, Schorle, Capri-Sun, Fruit Whoop, smoothies: juice; milkshakes, shakes: milk |

The item's name is the chain's own in both languages (`names`), in the chain's
capitalisation without its ® and ™ ("Big Mac", "Whopper"), and the builder adds
what people call it beside that: a count read either side ("McNuggets 6er", "King
Nuggets 6er") and the
fries by size ("Pommes mittel", "medium fries"). A food is one item at its published
weight; a drink whose name states its size ("0,5l", "250 ml") is measured by volume at
that size, and one that states none ("Café Grande", "Mezzo Mix") is one serving at its
published weight. An item whose chain states no weight is never given one: a row of
per-portion figures is one serving (basis `perServing`), a row stated per 100 g only opens
at 100 g (a row per 100 ml at 100 ml), and the note says the chain states no weight or
portion.

In the app, `ChainCatalog` loads the file through `FoodDataFiles`; its records are
café-sourced products, found by name and chain ("Big Mac", "McNuggets 6er",
"McDonald's Big Mac"), and a description that names an item outright ("1 Big Mac") is
the chain's item ahead of a national table's row of the same name. The app shows the name
as the chain spells it, never in the sentence case it gives other names, and a search that
names a chain lists its items first in Branded, ahead of retail packs. A row that is the same
product as a chain item among the results folds into it: a national table's row of it
(CoFID's "Big Mac", USDA's "Big Mac, McDonald's") or a pack whose brand is the chain under
the item's name; a product with a brand of its own (Iceland's "Greggs Sausage Rolls") stays,
and the meal parser never offers the folded rows beside the item. A name that is also one
of Akari's own foods (a reviewed food, a recipe or a generic café drink: "Cappuccino",
"Hamburger", "Ketchup"), also before a "mit" or "with" ("Cappuccino mit Milch"), names the
chain's item only together with the chain ("Burger King Cappuccino"). The nutrition is the
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
