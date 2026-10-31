#!/usr/bin/env python3
"""Publication gate: compatible schemas, complete files, and reported provenance."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

REFERENCE_SOURCES = {"bls", "usda", "cofid", "ciqual", "mext"}


def verify_reference_coverage(source_counts, verified_counts):
    """Reject incomplete reference indexes without pinning normal count growth."""
    sources = set(source_counts)
    if sources != REFERENCE_SOURCES:
        raise ValueError(
            f"Reference sources differ: expected {sorted(REFERENCE_SOURCES)}, "
            f"got {sorted(sources)}"
        )
    empty_sources = sorted(source for source, count in source_counts.items() if count <= 0)
    if empty_sources:
        raise ValueError(f"Empty reference sources: {empty_sources}")
    verified_sources = set(verified_counts)
    if verified_sources != sources:
        raise ValueError(
            f"Verified reference coverage differs: expected {sorted(sources)}, "
            f"got {sorted(verified_sources)}"
        )
    invalid_counts = {
        source: (verified_counts[source], source_counts[source])
        for source in sources
        if not 0 < verified_counts[source] <= source_counts[source]
    }
    if invalid_counts:
        raise ValueError(
            "Invalid verified/total reference counts: "
            + ", ".join(
                f"{source}={verified}/{total}"
                for source, (verified, total) in sorted(invalid_counts.items())
            )
        )


def verify_rejections(directory, market, asset):
    """A market that reports rejected products (b220) ships the sidecar that
    lists them, one JSON line per barcode with its rule, and the lines match
    the counts, so a wrong rejection can always be looked up."""
    rejected = asset.get('rejected')
    if rejected is None:
        return
    filename = asset.get('rejectedFilename') or f'rejected-{market.lower()}.jsonl'
    if Path(filename).name != filename: raise ValueError('Invalid sidecar filename: '+market)
    path = directory / filename
    if not path.exists(): raise ValueError('Missing rejection sidecar: '+market)
    counts = {}
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            if not entry.get('code') or not entry.get('rule'):
                raise ValueError('Malformed rejection line: '+market)
            counts[entry['rule']] = counts.get(entry['rule'], 0) + 1
    if counts != {rule: count for rule, count in rejected.items() if count}:
        raise ValueError('Rejection sidecar does not match the manifest counts: '+market)


def verify(directory):
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest.get('schemaVersion')!=4:raise ValueError('Expected schema 4')
    if not manifest.get('markets'):raise ValueError('No market catalogues')
    for market,asset in manifest['markets'].items():
        filename=asset['filename']
        if Path(filename).name!=filename:raise ValueError('Invalid asset filename')
        path=directory/filename
        if path.stat().st_size!=asset['bytes']:raise ValueError('Wrong size: '+market)
        with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=asset['sha256']:raise ValueError('Wrong hash: '+market)
        db=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
        metadata=dict(db.execute('SELECT key,value FROM metadata'))
        if metadata.get('nutrition_provenance')!='reported-json-input-sets':
            raise ValueError('Refusing unverified/CSV nutrient provenance: '+market)
        if db.execute('PRAGMA user_version').fetchone()[0]!=4:raise ValueError('Wrong schema')
        if db.execute('PRAGMA application_id').fetchone()[0]!=1095451218:raise ValueError('Wrong application')
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Corrupt SQLite')
        if metadata.get('market')!=market:raise ValueError('Wrong market')
        for table,key in [('family','familyCount'),('sku','skuCount')]:
            if asset[key] <= 0:raise ValueError('Empty market catalogue: '+market)
            if db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]!=asset[key]:raise ValueError('Wrong count')
        if db.execute('SELECT count(*) FROM sku WHERE NOT json_valid(nutrients_json)').fetchone()[0]:raise ValueError('Malformed nutrients')
        db.close()
        verify_rejections(directory, market, asset)
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
    result=verify(a.directory);print('Verified',len(result['markets']),'market files and reported-nutrition provenance')
