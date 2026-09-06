"""Deterministic, presentation-only food types shared with the iOS app.

No nutrition/ingredient inference. The rules file is the owned classification;
OFF tags and manufacturer-reviewed product lines are evidence for decisions.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

RULES_PATH = Path(__file__).with_name('artwork-classification.json')
MANIFEST = json.loads(RULES_PATH.read_text())
VERSION = MANIFEST['version']

def normalize(value):
    value = unicodedata.normalize('NFD', value or '').casefold()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in value
                           if not unicodedata.combining(c)).split())

def strings(value):
    if isinstance(value, str): return [v.strip() for v in value.split(',') if v.strip()]
    return [v for v in (value or []) if isinstance(v, str)]

RULES = [{**r, 'terms': [normalize(t) for t in r['terms']]} for r in MANIFEST['rules']]
BY_ID = {r['id']: r for r in RULES}
TAG_RULES = {tag: rule for rule in RULES for tag in rule['tags']}
LINES = [{**r, 'aliases': [normalize(a) for a in r['aliases']],
          'allowed': set(normalize(' '.join(r['qualifiers'])).split())} for r in MANIFEST['productLines']]

def resolve(matches, source):
    if not matches: return None
    priority = max(r['priority'] for r, _ in matches)
    best = [(r, e) for r,e in matches if r['priority'] == priority]
    if len({r['id'] for r,_ in best}) != 1: return None
    rule, evidence = sorted(best, key=lambda x: x[1])[0]
    return dict(categoryID=rule['id'], artworkID=rule['artworkID'], source=source,
                evidence=evidence, version=VERSION)

def by_name(name, source):
    subject = normalize(name)
    subject = re.split(r' (?:with|without|in|mit|ohne|avec|sans) ', subject)[0]
    padded = f' {subject} '
    matches = [(r,t) for r in RULES for t in r['terms'] if f' {t} ' in padded]
    # Longer phrases suppress contained aliases (peanut butter, iced tea).
    matches = [(r,t) for r,t in matches if not any(len(u)>len(t) and f' {t} ' in f' {u} ' for _,u in matches)]
    return resolve(matches, source)

def classify(name, brand=None, generic_name=None, category_tags=(), categories=()):
    tags = strings(category_tags)
    matches = [(TAG_RULES[t],t) for t in tags if t in TAG_RULES]
    # Unmapped/conflicting source tags must not silently fall through to a brand guess.
    category = resolve(matches, 'category-tag')
    if matches and category is None: return None
    named = by_name(name, 'product-name')
    if category:
        # Explicit finished forms beat broad ingredient tags in incomplete records.
        if named and BY_ID[named['categoryID']]['priority'] >= 80 and BY_ID[named['categoryID']]['priority'] > BY_ID[category['categoryID']]['priority']:
            return named
        return category
    if generic_name and (result := by_name(generic_name, 'generic-name')):
        if named and BY_ID[named['categoryID']]['priority'] >= 80 and BY_ID[named['categoryID']]['priority'] > BY_ID[result['categoryID']]['priority']:
            return named
        return result
    label_matches = []
    for label in strings(categories):
        normalized = normalize(label)
        for rule in RULES:
            labels = {normalize(tag.split(':',1)[-1]) for tag in rule['tags']} | set(rule['terms'])
            if rule['id'] == 'cereal': labels -= {'cereal','cereals'}
            if normalized in labels: label_matches.append((rule,label))
    if label_matches:
        return resolve(label_matches, 'category-label')
    normalized_name = normalize(re.sub(r'\b\d+(?:[.,]\d+)?\s*(?:kg|g|ml|cl|l|oz)\b', '', name, flags=re.I))
    brand_names = {normalize(b) for b in strings(brand)}
    for line in LINES:
        for alias in line['aliases']:
            padded = f' {normalized_name} '
            if alias not in brand_names and f' {alias} ' not in padded: continue
            rest = padded.replace(f' {alias} ', ' ').split()
            if all(word in line['allowed'] or word.isdecimal() for word in rest):
                rule = BY_ID[line['category']]
                return dict(categoryID=rule['id'],artworkID=rule['artworkID'],source='reviewed-product-line',evidence=line['id'],version=VERSION)
    return named

def classify_record(record):
    return classify(record.get('product_name',''),record.get('brands'),record.get('generic_name'),
                    record.get('categories_tags',[]),record.get('categories',[]))
