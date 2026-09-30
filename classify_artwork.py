"""Deterministic, presentation-only food types shared with the iOS app.

No nutrition/ingredient inference. The rules file is the owned classification;
OFF tags and manufacturer-reviewed product lines are evidence for decisions.
"""
from __future__ import annotations
import json
import functools
from food_taxonomy import CATALOG, most_specific
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

RULES = [{**r, 'terms': [normalize(t) for t in r['terms']],
          'exactTerms': [normalize(t) for t in r.get('exactTerms', [])]}
         for r in MANIFEST['rules']]
BY_ID = {r['id']: r for r in RULES}
COMPOUND_RULES = [(r, [normalize(s) for s in r['compoundSuffixes']],
                  [normalize(s) for s in r.get('compoundExclusions', [])])
                 for r in RULES if r.get('compoundSuffixes')]
TAG_RULES = {tag: BY_ID[category] for tag, category in CATALOG['tags'].items() if category in BY_ID}
TAG_RULES.update({tag: rule for rule in RULES for tag in rule['tags']})
LABEL_CANDIDATES = {label: [BY_ID[category]] for label, category in CATALOG['labels'].items() if category in BY_ID}
for rule in RULES:
    labels = ({normalize(tag.split(':',1)[-1]) for tag in rule['tags']}
              | set(rule['terms']) | set(rule['exactTerms']))
    if rule['id'] == 'cereal': labels -= {'cereal','cereals'}
    for label in labels: LABEL_CANDIDATES.setdefault(label, []).append(rule)
LABEL_RULES = {}
for label, candidates in LABEL_CANDIDATES.items():
    priority = max(r['priority'] for r in candidates)
    best = [r for r in candidates if r['priority'] == priority]
    if len({r['id'] for r in best}) == 1: LABEL_RULES[label] = best[0]
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

@functools.lru_cache(maxsize=100000)
def by_name(name, source):
    subject = food_subject(name)
    primary = matching_subject(subject, source)
    if primary and ',' in name:
        head = normalize(name.split(',', 1)[0])
        if any(head in r['terms'] or head in r['exactTerms'] for r in RULES):
            identity = matching_subject(head, source)
            if identity and (owns_identity(primary, identity) or owns_identity(identity, primary)):
                return identity
    full = food_subject(name, removing_parentheses=False)
    if full != subject and (not primary or primary['categoryID'] == 'prepared-meal'):
        return matching_subject(full, source) or primary
    return primary

def matching_subject(subject, source):
    if rule := LABEL_RULES.get(subject): return resolve([(rule,subject)], source)
    padded = f' {subject} '
    matches = ([(r,t) for r in RULES for t in r['terms'] if f' {t} ' in padded]
               + [(r,t) for r in RULES for t in r['exactTerms'] if subject == t])
    literal_words = {t for _, t in matches}
    for rule, suffixes, exclusions in COMPOUND_RULES:
        for word in subject.split():
            if word not in literal_words and not any(word.endswith(s) for s in exclusions) and any(
                    len(word) >= len(s) + 3 and word.endswith(s) for s in suffixes):
                matches.append((rule, word))
    # Longer phrases suppress contained aliases (peanut butter, iced tea).
    matches = [(r,t) for r,t in matches if not any(len(u)>len(t) and f' {t} ' in f' {u} ' for _,u in matches)]
    # Finished food forms own their ingredients/flavors, independently of priority.
    matches = [(r,t) for r,t in matches if not any(
        r['id'] in owner.get('ingredientCategories', []) for owner,_ in matches)]
    return resolve(matches, source)

def owns_identity(named, other):
    return named and other['categoryID'] in BY_ID[named['categoryID']].get('ingredientCategories', [])

def is_exact_name_match(classification, name):
    return (classification and classification['source'] == 'product-name'
            and normalize(classification['evidence']) == food_subject(name))

def food_subject(name, removing_parentheses=True):
    if removing_parentheses and '(' in name and name.index('(') > 0:
        name = re.sub(r'\([^)]*\)', ' ', name)
    # Explicitly absent accompaniments do not own the food's artwork. This
    # keeps USDA salads ending in "no dressing" on the salad bowl rather than
    # the sauce jar, while an actual "salad dressing" still remains a sauce.
    name = re.sub(r'\bno\s+(?:dressing|sauce)\b', ' ', name, flags=re.IGNORECASE)
    return re.split(r' (?:with|without|in|im|mit|ohne|for|fur|avec|sans|dans|au jus) ', normalize(name))[0]

def is_meat_alternative(name):
    subject = food_subject(name, removing_parentheses=False)
    padded = f' {subject} '
    return any(f' {normalize(marker)} ' in padded for marker in MANIFEST['meatAlternativeMarkers'])

def classify(name, brand=None, generic_name=None, category_tags=(), categories=()):
    result = classify_identity(name, brand, generic_name, category_tags, categories)
    alternative_tag = next((tag for tag in strings(category_tags) if tag in MANIFEST['meatAlternativeTags']), None)
    alternative = is_meat_alternative(name) or alternative_tag is not None
    if result and result['artworkID'] in ('meat', 'meat-on-bone', 'poultry', 'bacon') and alternative:
        return resolve([(BY_ID['meat-alternative'], alternative_tag or name)],
                       'category-tag' if alternative_tag else 'product-name')
    return result

def classify_identity(name, brand=None, generic_name=None, category_tags=(), categories=()):
    tags = strings(category_tags)
    matches = [(TAG_RULES[t],t) for t in most_specific(t for t in tags if t in TAG_RULES)]
    # Unmapped/conflicting source tags must not silently fall through to a brand guess.
    category = resolve(matches, 'category-tag')
    if matches and category is None: return None
    named = by_name(name, 'product-name')
    if category:
        # Source metadata can be wrong. An unambiguous complete food name is
        # stronger evidence than a contradictory category tag.
        if (is_exact_name_match(named, name)
                and category['categoryID'] in BY_ID[named['categoryID']].get('overridesCategories', [])):
            return named
        if owns_identity(named, category): return named
        # Explicit finished forms beat broad ingredient tags in incomplete records.
        if named and (BY_ID[named['categoryID']]['priority'] >= 80 or category['categoryID'] == 'prepared-meal') and BY_ID[named['categoryID']]['priority'] > BY_ID[category['categoryID']]['priority']:
            return named
        return category
    generic_rule = LABEL_RULES.get(normalize(generic_name)) if generic_name else None
    generic = resolve([(generic_rule, generic_name)], 'generic-name') if generic_rule else by_name(generic_name or '', 'generic-name')
    if generic_name and (result := generic):
        if owns_identity(named, result): return named
        if named and BY_ID[named['categoryID']]['priority'] >= 80 and BY_ID[named['categoryID']]['priority'] > BY_ID[result['categoryID']]['priority']:
            return named
        return result
    label_matches = []
    for label in strings(categories):
        normalized = normalize(label)
        if rule := LABEL_RULES.get(normalized): label_matches.append((rule,label))
    if label_matches:
        label = resolve(label_matches, 'category-label')
        if label and owns_identity(named, label): return named
        return label
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
