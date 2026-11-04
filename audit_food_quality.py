#!/usr/bin/env python3
"""Audit every retained SKU and every national reference without inventing values.

Cross-market agreement on the same OFF barcode is consistency, not independent
confirmation. National-table comparisons flag disagreements for review; they
never replace a manufacturer's label or prove brand-specific micronutrients.
"""
import argparse
import collections
import hashlib
import json
import sqlite3
from pathlib import Path
from build_index import SUPPORTED_NUTRIENTS, MICRONUTRIENTS, validation_issues, normalized_text, GRAM_NUTRIENTS, MILLIGRAM_NUTRIENTS, MICROGRAM_NUTRIENTS
from classify_artwork import classify, VERSION
from food_taxonomy import CATALOG, most_specific


def macro_similarity(declared, reference):
    errors=[]; energy_error=None
    for nutrient, floor in [('calories',50),('protein',5),('fat',5),('carbs',5)]:
        if nutrient not in declared or nutrient not in reference: continue
        a,b=declared[nutrient],reference[nutrient]
        error=abs(a-b)/max(abs(a),abs(b),floor)
        errors.append(error)
        if nutrient=='calories': energy_error=error
    if len(errors)<3 or energy_error is None or energy_error>.12 or max(errors)>.35: return None
    mean=sum(errors)/len(errors)
    return 1-mean if mean<=.12 else None


def load_references(path):
    db=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    references={i:dict(id=i,source=s,name=n,alternateName=a,nutrients=json.loads(v))
                for i,s,n,a,v in db.execute('SELECT id,source,name,alternate_name,nutrients_json FROM reference_food')}
    db.close();return references


def reference_audit(references):
    counts=collections.Counter(); missing=collections.defaultdict(collections.Counter)
    issues=[]; issue_counts=collections.Counter(); identities=collections.defaultdict(dict)
    for ref in references.values():
        counts[ref['source']]+=1
        for nutrient in SUPPORTED_NUTRIENTS:
            if nutrient not in ref['nutrients']: missing[ref['source']][nutrient]+=1
        errors=validation_issues(ref['nutrients'])
        issue_counts.update(errors)
        if errors and len(issues)<100: issues.append(dict(id=ref['id'],name=ref['name'],issues=errors))
        for name in [ref['name'],ref['alternateName']]:
            if name: identities[normalized_text(name)][ref['id']]=ref
    compared=0; discordant=[]; seen=set()
    for identity,refs in sorted(identities.items()):
        values=list(refs.values())
        for i,a in enumerate(values):
            for b in values[i+1:]:
                pair=tuple(sorted((a['id'],b['id'])))
                if a['source']==b['source'] or pair in seen: continue
                seen.add(pair); compared+=1
                if macro_similarity(a['nutrients'],b['nutrients']) is None:
                    if len(discordant)<100: discordant.append(dict(identity=identity,referenceIDs=pair,reason='macro-profile-disagrees'))
    return dict(recordsBySource=dict(counts),missingNutrientsBySource=dict(missing),
                exactNamePairsAcrossNationalSources=compared,disagreementExamples=discordant,
                plausibilityIssues=dict(issue_counts),plausibilityReviewExamples=issues)


def audit_market(path,references,barcodes,reclassify=False):
    db=sqlite3.connect(path) if reclassify else sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    counts=collections.Counter(); source=collections.Counter(); missing=collections.Counter()
    validation=collections.Counter(); nutrient_disagreements=collections.Counter()
    examples=[]; unresolved=[]; changed=[]; cleaned=[]; quarantined=[]; quarantine_counts=collections.Counter()
    rows=db.execute('SELECT id,barcode,product_name,brand,generic_name,category_tags_json,categories_json,nutrients_json,nutrition_basis,artwork_classification_json,validation_json FROM sku')
    for row_id,code,name,brand,generic,tags,labels,payload,basis,stored,flags in rows:
        tags=json.loads(tags);labels=json.loads(labels);nutrients=json.loads(payload)
        invalid = {key:value for key,value in nutrients.items() if basis=='per100Grams' and (
            (key in GRAM_NUTRIENTS and value>100) or
            (key in MILLIGRAM_NUTRIENTS and value>100_000) or
            (key in MICROGRAM_NUTRIENTS and value>100_000_000))}
        if invalid:
            quarantine_counts.update(invalid.keys())
            quarantined.append(dict(barcode=code,name=name,values=invalid))
            new_flags=sorted(set(json.loads(flags)) | {'invalid-'+key for key in invalid})
            nutrients={key:value for key,value in nutrients.items() if key not in invalid}
            flags=json.dumps(new_flags)
            if reclassify:
                cleaned.append((json.dumps(nutrients,separators=(',',':')),len(nutrients),
                                len(MICRONUTRIENTS.intersection(nutrients)),flags,row_id))
        result=classify(name,brand,generic,tags,labels)
        counts['skuRecords']+=1
        if tags: counts['withCategoryTags']+=1
        if result:
            counts['classified']+=1;source[result['source']]+=1
            if result['artworkID']!='plate': counts['specificArtwork']+=1
        elif len(unresolved)<100: unresolved.append(dict(barcode=code,name=name,brand=brand,categoryTags=tags))
        if reclassify and result != json.loads(stored or '{}'):
            changed.append((json.dumps(result or {},ensure_ascii=False,separators=(',',':')),row_id))
        for nutrient in SUPPORTED_NUTRIENTS:
            if nutrient not in nutrients: missing[nutrient]+=1
        if len(MICRONUTRIENTS.intersection(nutrients))>=10: counts['atLeastTenDeclaredMicronutrients']+=1
        errors=set(json.loads(flags)) | set(validation_issues(nutrients,basis))
        validation.update(errors)
        fingerprint=hashlib.sha256((basis+json.dumps(nutrients,sort_keys=True,separators=(',',':'))).encode()).hexdigest()
        if code in barcodes:
            counts['sharedBarcodeComparisons']+=1
            if barcodes[code]!=fingerprint: counts['crossMarketNutrientConflicts']+=1
        else: barcodes[code]=fingerprint
        specific=most_specific(tags)
        links={CATALOG['referenceLinks'][tag]['referenceCode'] for tag in specific if tag in CATALOG['referenceLinks']}
        if len(links)!=1 or basis!='per100Grams': continue
        ref=references.get(next(iter(links)))
        if not ref: continue
        counts['specificSourceReferenceLink']+=1
        if macro_similarity(nutrients,ref['nutrients']) is None:
            counts['linkedReferenceMacroMismatch']+=1;continue
        counts['linkedReferenceMacroMatch']+=1
        for nutrient in MICRONUTRIENTS.intersection(nutrients).intersection(ref['nutrients']):
            a,b=nutrients[nutrient],ref['nutrients'][nutrient]
            counts['declaredMicroReferenceComparisons']+=1
            # Broad audit threshold, not a deletion rule or a nutritional claim.
            floor=1 if nutrient in {'vitaminB12','vitaminD'} else 10
            if max(a,b)>max(min(a,b)*4,floor):
                nutrient_disagreements[nutrient]+=1
                if len(examples)<100:
                    examples.append(dict(barcode=code,name=name,nutrient=nutrient,declared=a,
                                         reference=b,referenceCode=ref['id'],reason='review-source-or-fortification'))
    if reclassify:
        db.executemany('UPDATE sku SET artwork_classification_json=? WHERE id=?',changed)
        db.executemany('UPDATE sku SET nutrients_json=?,nutrient_count=?,micronutrient_count=?,validation_json=? WHERE id=?',cleaned)
        db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('classification_version',?)",(str(VERSION),))
        db.commit()
    integrity=db.execute('PRAGMA quick_check').fetchone()[0];db.close()
    return dict(file=path.name,counts=dict(counts),classificationEvidence=dict(source),
                missingDeclaredNutrients=dict(missing),validationIssues=dict(validation),
                micronutrientReferenceDisagreements=dict(nutrient_disagreements),
                disagreementExamples=examples,unresolvedExamples=unresolved,
                reclassifiedRows=len(changed),quarantinedValuesByNutrient=dict(quarantine_counts),
                quarantineExamples=quarantined,sqliteIntegrity=integrity)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path);p.add_argument('--references',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--reclassify',action='store_true')
    a=p.parse_args(); refs=load_references(a.references);barcodes={};markets=[]
    for path in sorted(a.directory.glob('akari-food-*.sqlite')):
        item=audit_market(path,refs,barcodes,a.reclassify);markets.append(item)
        print(path.name,item['counts'],flush=True)
    result=dict(scope='All retained SKU records in every supplied market and all bundled national references. Repeated barcodes across markets are not independent nutrition evidence. Coverage is not accuracy. Missing is not zero.',
                uniqueBarcodes=len(barcodes),classificationVersion=VERSION,taxonomySource=CATALOG['source'],
                nationalReferences=reference_audit(refs),markets=markets)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if a.reclassify:
        manifest_path=a.directory/'manifest.json';manifest=json.loads(manifest_path.read_text())
        for asset in manifest['markets'].values():
            path=a.directory/asset['filename']; asset['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            asset['bytes']=path.stat().st_size
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
