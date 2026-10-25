#!/usr/bin/env python3
"""Publish v4 beside a pinned legacy manifest, keeping installed apps working."""
import argparse
import json
from pathlib import Path


def prepare(directory, previous_manifest, previous_tag, base_url, output=None):
    """Stage both manifests for base_url. With output, write them there and leave
    the build untouched, so another host's copy can be staged first; without it,
    rename the databases to their -v4 names and replace the build manifest."""
    current_path=directory/'manifest.json'
    current=json.loads(current_path.read_text())
    legacy=json.loads(previous_manifest.read_text())
    if current['schemaVersion'] != 4 or legacy['schemaVersion'] not in (1,2,3):
        raise ValueError('Expected a v4 build and an existing legacy manifest')
    for asset in current['markets'].values():
        old_name=asset['filename']
        if Path(old_name).name != old_name: raise ValueError('Invalid filename')
        new_name=Path(old_name).stem+'-v4.sqlite'
        if output is None: (directory/old_name).rename(directory/new_name)
        asset['filename']=new_name
        asset['url']=base_url.rstrip('/')+'/'+new_name
    for asset in legacy['markets'].values():
        # Preserve immutable URLs on later runs; pin only the first migration.
        asset['url']=asset['url'].replace('/releases/latest/download/',
                                         f'/releases/download/{previous_tag}/')
    target=output or directory
    target.mkdir(parents=True,exist_ok=True)
    (target/'manifest-v4.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    (target/'manifest.json').write_text(json.dumps(legacy,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',required=True,type=Path)
    p.add_argument('--previous-manifest',required=True,type=Path)
    p.add_argument('--previous-tag',required=True)
    p.add_argument('--base-url',required=True)
    p.add_argument('--output',type=Path,help='write the manifests here and leave the build untouched')
    a=p.parse_args()
    prepare(a.directory,a.previous_manifest,a.previous_tag,a.base_url,a.output)
