"""Source-backed category identities, translations and cross-checked Ciqual links."""
import functools
import json
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name('food-category-taxonomy.json').read_text())

@functools.lru_cache(maxsize=20000)
def ancestors(tag):
    result = set()
    for parent in CATALOG['parents'].get(tag, []):
        result.add(parent); result.update(ancestors(parent))
    return frozenset(result)


def most_specific(tags):
    tags = set(tags)
    inherited = set().union(*(ancestors(tag) for tag in tags)) if tags else set()
    return sorted(tags - inherited)


def search_names(tags):
    # Specific identities only: 'fermented food' must not become a useful alias
    # for every cheese. Never index ingredient names as the product identity.
    return list(dict.fromkeys(name for tag in most_specific(tags)
                             for name in CATALOG['names'].get(tag, {}).values()))
