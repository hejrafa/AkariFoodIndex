#!/usr/bin/env python3
"""Publish v4 beside a pinned legacy manifest, keeping installed apps working."""
import argparse
import json
from pathlib import Path


def prepare(directory, previous_manifest, previous_tag, base_url):
    current_path=directory/'manifest.json'
    current=json.loads(current_path.read_text())
    legacy=json.loads(previous_manifest.read_text())
    if current['schemaVersion'] != 4 or legacy['schemaVersion'] not in (1,2,3):
        raise ValueError('Expected a v4 build and an existing legacy manifest')
    for asset in current['markets'].values():
        old_name=asset['filename']
        if Path(old_name).name != old_name: raise ValueError('Invalid filename')
        new_name=Path(old_name).stem+'-v4.sqlite'
        (directory/old_name).rename(directory/new_name)
        asset['filename']=new_name
        asset['url']=base_url.rstrip('/')+'/'+new_name
    for asset in legacy['markets'].values():
        # Preserve immutable URLs on later runs; pin only the first migration.
        asset['url']=asset['url'].replace('/releases/latest/download/',
                                         f'/releases/download/{previous_tag}/')
    (directory/'manifest-v4.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    current_path.write_text(json.dumps(legacy,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',required=True,type=Path)
    p.add_argument('--previous-manifest',required=True,type=Path)
    p.add_argument('--previous-tag',required=True)
    p.add_argument('--base-url',required=True)
    a=p.parse_args()
    prepare(a.directory,a.previous_manifest,a.previous_tag,a.base_url)
