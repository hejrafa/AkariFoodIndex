"""Read reported nutrition without promoting OFF recipe estimates to label facts.

OFF's v3 input_sets retain source, preparation, amount and unit. Its aggregated
set (and flattened CSV export) can mix packaging with estimates. Only packaging
and manufacturer input sets are eligible here; prepared sets, percent-DV values,
unknown units and guessed density conversions are excluded.

Reference: https://openfoodfacts.github.io/openfoodfacts-server/dev/ref-perl-pod/ProductOpener/Nutrition.html
"""
import math

MASS_TO_GRAMS={'g':1,'mg':.001,'µg':.000001,'μg':.000001,'ug':.000001,'kg':1000}
AMOUNT_UNITS={'g':('per100Grams',1),'kg':('per100Grams',1000),
              'ml':('per100Milliliters',1),'cl':('per100Milliliters',10),
              'dl':('per100Milliliters',100),'l':('per100Milliliters',1000)}


def number(value):
    if isinstance(value,bool):return None
    try: value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) and value>=0 else None


def normalize_record(record):
    nutrition=record.get('nutrition')
    if not isinstance(nutrition,dict):return record  # Legacy JSON nutriments is separate from nutriments_estimated.
    groups={}; newest={}; sources=set()
    sets=nutrition.get('input_sets')
    if not isinstance(sets,list):sets=[]
    eligible=[s for s in sets if isinstance(s,dict) and s.get('source') in ('packaging','manufacturer')
              and s.get('preparation')=='as_sold']
    # The latest reported value for the same basis wins; retain declared zero.
    for item in sorted(eligible,key=lambda s:(number(s.get('last_updated_t')) or 0,s.get('source')=='manufacturer')):
        per=item.get('per');unit=str(item.get('per_unit','')).lower()
        amount=number(item.get('per_quantity'))
        if per in ('100g','100ml'):
            expected='g' if per=='100g' else 'ml'
            if unit and unit!=expected:continue
            unit=expected;amount=100
        if unit not in AMOUNT_UNITS or amount is None or amount<=0:continue
        basis,factor=AMOUNT_UNITS[unit]; scale=100/(amount*factor)
        target=groups.setdefault(basis,{})
        newest[basis]=max(newest.get(basis,0),number(item.get('last_updated_t')) or 0)
        for key,entry in (item.get('nutrients') or {}).items():
            if not isinstance(entry,dict):continue
            value=number(entry.get('value'))  # value_computed is deliberately not the label.
            if value is None:continue
            nutrient_unit=str(entry.get('unit','')).strip().lower()
            if key in ('energy','energy-kcal','energy-kj'):
                if nutrient_unit=='kcal': canonical='energy-kcal';conversion=1
                elif nutrient_unit=='kj': canonical='energy-kj';conversion=1
                else:continue
            else:
                if nutrient_unit not in MASS_TO_GRAMS:continue
                canonical=key;conversion=MASS_TO_GRAMS[nutrient_unit]
            target[canonical+'_100g']=value*conversion*scale
            sources.add(item['source'])
    def rank(basis):
        data=groups[basis]
        return (sum(k in data for k in ('energy-kcal_100g','proteins_100g','fat_100g','carbohydrates_100g')),
                'energy-kcal_100g' in data or 'energy-kj_100g' in data,len(data),newest[basis])
    basis=max(groups,key=rank) if groups else 'per100Grams'
    result=dict(record)
    result['nutriments']=groups.get(basis,{})
    result['nutrition_data_per']='100ml' if basis=='per100Milliliters' else '100g'
    result['_akari_nutrition_provenance']='reported-input-sets:'+','.join(sorted(sources))
    return result
