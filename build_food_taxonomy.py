#!/usr/bin/env python3
"""Compile OFF's reviewed category graph; keep presentation and nutrient links separate.

A direct Ciqual code is only accepted when the supplied French food name agrees
with the actual bundled ANSES record. Proxy/environmental codes are never used.
This is a source identity cross-check, not independent laboratory validation.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path


def normalize(value):
    value = unicodedata.normalize('NFD', value or '').casefold()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in value
                           if not unicodedata.combining(c)).split())


def compile_taxonomy(taxonomy, manifest, references):
    rules = {r['id']: r for r in manifest['rules']}
    seeds = {t: r['id'] for r in manifest['rules'] for t in r['tags']}
    parents = {k: d.get('parents', []) for k, d in taxonomy.items()}
    memo = {}
    def ancestors(tag, visiting=frozenset()):
        if tag in memo: return memo[tag]
        if tag in visiting: raise ValueError('Category taxonomy contains a cycle: '+tag)
        result = {tag}
        for parent in parents.get(tag, []): result |= ancestors(parent, visiting | {tag})
        memo[tag] = result
        return result
    tags = {}
    names = {}
    label_candidates = collections.defaultdict(set)
    links = {}
    rejected = collections.Counter()
    rejected_examples = []
    for tag, entry in sorted(taxonomy.items()):
        # An explicit child food (oat flakes, cream cheese) owns its identity;
        # a higher-priority broad ancestor must not turn it into flour or milk.
        seed_tags = {a for a in ancestors(tag) if a in seeds}
        inherited_seeds = set().union(*(ancestors(a) - {a} for a in seed_tags)) if seed_tags else set()
        matches = {seeds[a] for a in seed_tags - inherited_seeds}
        if matches:
            priority = max(rules[c]['priority'] for c in matches)
            best = {c for c in matches if rules[c]['priority'] == priority}
            if len(best) == 1: tags[tag] = next(iter(best))
        values = {lang: name for lang, name in entry.get('name', {}).items()
                  if lang in ('en', 'de', 'fr', 'it', 'es', 'nl', 'pt')}
        if values: names[tag] = values
        if tag in tags:
            for name in values.values(): label_candidates[normalize(name)].add(tags[tag])
        code = entry.get('ciqual_food_code', {}).get('en')
        if not code: continue
        reference_id = 'ciqual:'+str(code)
        reference_name = references.get(reference_id)
        french = entry.get('ciqual_food_name', {}).get('fr', '')
        reason = None
        if not reference_name: reason = 'reference-code-not-in-current-ciqual'
        elif not french: reason = 'missing-reference-name-cross-check'
        elif normalize(french) != normalize(reference_name): reason = 'reference-name-disagrees'
        elif any(p in normalize(reference_name) for p in ('aliment moyen', 'sans precision')):
            reason = 'unspecified-average-reference'
        if reason:
            rejected[reason] += 1
            if len(rejected_examples) < 80:
                rejected_examples.append(dict(tag=tag, referenceCode=reference_id, reason=reason,
                                              taxonomyName=french, referenceName=reference_name))
        else:
            links[tag] = dict(referenceCode=reference_id, referenceName=reference_name)
    labels = {k: next(iter(v)) for k, v in sorted(label_candidates.items()) if len(v) == 1}
    return dict(version=1, classificationVersion=manifest['version'], tags=tags,
                labels=labels, names=names, parents=parents, referenceLinks=links), dict(
                    taxonomyCategories=len(taxonomy), mappedCategories=len(tags),
                    exactLocalizedLabels=len(labels), crossCheckedReferenceLinks=len(links),
                    rejectedReferenceLinks=dict(rejected), rejectedExamples=rejected_examples)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--taxonomy', required=True, type=Path)
    p.add_argument('--reference-index', required=True, type=Path)
    p.add_argument('--rules', type=Path, default=Path(__file__).with_name('artwork-classification.json'))
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    a=p.parse_args()
    db=sqlite3.connect(f'file:{a.reference_index}?mode=ro',uri=True)
    refs=dict(db.execute("SELECT id,name FROM reference_food WHERE source='ciqual'")); db.close()
    result, report=compile_taxonomy(json.loads(a.taxonomy.read_text()),json.loads(a.rules.read_text()),refs)
    source=dict(url='https://static.openfoodfacts.org/data/taxonomies/categories.json',
                retrievedAt=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), sha256=hashlib.sha256(a.taxonomy.read_bytes()).hexdigest(),
                referenceSHA256=hashlib.sha256(a.reference_index.read_bytes()).hexdigest())
    result['source']=source; report['source']=source
    a.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print({k:v for k,v in report.items() if k not in ('source','rejectedExamples')})
if __name__=='__main__': main()
