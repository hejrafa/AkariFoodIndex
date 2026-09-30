"""Reject whole-food serving labels that contradict the product identity."""
import json
import re
import unicodedata
from pathlib import Path


def normalize(value):
    value = unicodedata.normalize('NFD', value or '').casefold()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in value
                           if not unicodedata.combining(c)).split())


GROUPS = [[normalize(x) for x in group] for group in json.loads(
    Path(__file__).with_name('serving-identities.json').read_text())['groups']]


def accepts(label, name, generic_name=None):
    label = (label or '').strip()
    if not label or not (label[0].isnumeric() or label[0] in '¼½¾⅓⅔⅛⅜⅝⅞'):
        return True
    words = normalize(label.split('(', 1)[0]).split()
    while words and words[0].isnumeric():
        words.pop(0)
    while words and words[0] in ('small', 'medium', 'large', 'kleine', 'klein', 'grosse', 'gross'):
        words.pop(0)
    group = next((g for g in GROUPS if ' '.join(words) in g), None)
    if group is None:
        return True
    for identity in (name, generic_name):
        subject = re.split(r' (?:with|mit|in|im|avec) ', normalize(identity))[0]
        if any(f' {alias} ' in f' {subject} ' for alias in group):
            return True
    return False
