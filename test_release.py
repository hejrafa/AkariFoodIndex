import json
import pathlib
import sys
import tempfile
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from prepare_release import prepare

class ReleaseCompatibilityTests(unittest.TestCase):
    def test_old_apps_keep_immutable_catalogue_and_new_apps_get_v4(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            for pinned in [False,True]:
                url='https://github.com/hejrafa/AkariFoodIndex/releases/'
                old_url=url+('download/original/' if pinned else 'latest/download/')+'akari-food-de.sqlite'
                previous={'schemaVersion':1,'markets':{'DE':{'filename':'akari-food-de.sqlite','url':old_url,'sha256':'old'}}}
                current={'schemaVersion':4,'markets':{'DE':{'filename':'akari-food-de.sqlite','url':'unused','sha256':'new'}}}
                (root/'previous.json').write_text(json.dumps(previous))
                (root/'manifest.json').write_text(json.dumps(current))
                (root/'akari-food-de.sqlite').write_bytes(b'new schema database')
                prepare(root,root/'previous.json','first',url+'latest/download')
                legacy=json.loads((root/'manifest.json').read_text())
                v4=json.loads((root/'manifest-v4.json').read_text())
                self.assertEqual(legacy['schemaVersion'],1)
                self.assertIn('/download/original/' if pinned else '/download/first/',legacy['markets']['DE']['url'])
                self.assertEqual(legacy['markets']['DE']['sha256'],'old')
                self.assertEqual(v4['markets']['DE']['filename'],'akari-food-de-v4.sqlite')
                self.assertEqual((root/'akari-food-de-v4.sqlite').read_bytes(),b'new schema database')
