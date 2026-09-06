#!/usr/bin/env python3
"""Publication gate: compatible schemas, complete files, and reported provenance."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


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
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
    result=verify(a.directory);print('Verified',len(result['markets']),'market files and reported-nutrition provenance')
