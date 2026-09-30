#!/usr/bin/env python3
"""Audit installed/release catalogues without changing source records.

Counts are rule coverage, not a claim of classification accuracy. Legacy v1/v2
catalogues have no identity tags; their audit can only measure name/brand rules.
"""
import argparse
import collections
import functools
import json
import sqlite3
from pathlib import Path
from classify_artwork import classify, VERSION

@functools.lru_cache(maxsize=100000)
def classify_cached(name, brand, generic, tags, categories):
    return classify(name,brand,generic,json.loads(tags),json.loads(categories))

def audit(path):
    database = sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    schema = database.execute('pragma user_version').fetchone()[0]
    columns = {r[1] for r in database.execute('pragma table_info(sku)')}
    extra = ', generic_name, category_tags_json, categories_json' if 'category_tags_json' in columns else ", NULL, '[]', '[]'"
    counts=collections.Counter(); categories=collections.Counter(); brands=collections.Counter()
    fol=[]; examples=[]
    for barcode,name,brand,generic,tags,labels in database.execute('select barcode, product_name, brand'+extra+' from sku'):
        result=classify_cached(name,brand,generic,tags,labels)
        counts['records']+=1
        if tags != '[]': counts['withCategoryTags']+=1
        if result:
            counts['classified']+=1; counts['source:'+result['source']]+=1
            categories[result['categoryID']]+=1
            if result['artworkID'] != 'plate': counts['specificArtwork']+=1
            else: counts['classifiedWithoutArtwork']+=1
        else:
            counts['unclassified']+=1;brands[brand or '(no brand)']+=1
        if 'fol epi' in (name+' '+(brand or '')).casefold():
            fol.append(dict(barcode=barcode,name=name,brand=brand,classification=result))
    # One review candidate per family, ordered by source quality; never an LLM guess.
    for row in database.execute('select s.barcode,s.product_name,s.brand'+extra.replace('generic_name','s.generic_name').replace('category_tags_json','s.category_tags_json').replace('categories_json','s.categories_json')+' from family f join sku s on s.id=f.representative_sku_id order by s.quality_score desc, s.barcode'):
        barcode,name,brand,generic,tags,labels=row
        result=classify_cached(name,brand,generic,tags,labels)
        if result is None or result['artworkID']=='plate':
            examples.append(dict(barcode=barcode,name=name,brand=brand,categoryTags=json.loads(tags),classification=result))
        if len(examples)>=200: break
    family_count=database.execute('select count(*) from family').fetchone()[0]
    database.close()
    return dict(file=path.name,schemaVersion=schema,ruleVersion=VERSION,families=family_count,
                counts=dict(counts),categories=dict(categories.most_common()),
                unclassifiedBrands=dict(brands.most_common(30)),folEpi=fol,reviewQueue=examples)

def audit_references(path):
    """Use the same primary/alternate identity fields as reference FoodProducts."""
    database = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    counts = collections.Counter()
    sources = collections.defaultdict(collections.Counter)
    categories = collections.Counter()
    examples = []
    for code, source, name, alternate in database.execute(
            'SELECT id, source, name, alternate_name FROM reference_food ORDER BY id'):
        result = classify(name, generic_name=alternate)
        outcome = 'specificArtwork' if result and result['artworkID'] != 'plate' else 'fallback'
        counts['records'] += 1
        counts[outcome] += 1
        sources[source]['records'] += 1
        sources[source][outcome] += 1
        if outcome == 'fallback':
            categories[result['categoryID'] if result else 'unknown'] += 1
            if len(examples) < 200:
                examples.append(dict(code=code, name=name, alternateName=alternate, classification=result))
    database.close()
    return dict(file=path.name, ruleVersion=VERSION, counts=dict(counts),
                bySource={key: dict(value) for key, value in sources.items()},
                fallbackCategories=dict(categories.most_common()), reviewQueue=examples)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--references', type=Path, help='Also audit the bundled reference-food SQLite database')
    args=parser.parse_args()
    results=[]
    for path in sorted(args.directory.glob('akari-food-*.sqlite')):
        result=audit(path);results.append(result)
        print(path.name,result['counts'],flush=True)
    report = dict(ruleVersion=VERSION,scope='All retained SKU records, counted per market; the same barcode can occur in multiple markets. Classification coverage is not measured accuracy.',markets=results)
    if args.references:
        report['references'] = audit_references(args.references)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__': main()
