import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from classify_artwork import classify, MANIFEST

class ArtworkClassificationTests(unittest.TestCase):
    def test_shared_regressions(self):
        for case in json.loads((ROOT/'classification-fixtures.json').read_text()):
            with self.subTest(case=case):
                result=classify(case['name'],case['brand'],case['genericName'],case['categoryTags'],case['categories'])
                self.assertEqual(result['categoryID'] if result else 'unknown',case['expected'])

    def test_rules_have_unique_tags_and_manufacturer_evidence(self):
        tags=[t for r in MANIFEST['rules'] for t in r['tags']]
        self.assertEqual(len(tags),len(set(tags)))
        for line in MANIFEST['productLines']:
            self.assertTrue(line['sourceURL'].startswith('https://'))
            self.assertTrue(line['reviewedAt'])
            self.assertIn(line['category'],[r['id'] for r in MANIFEST['rules']])

    def test_app_rules_and_fixtures_are_identical_when_checkout_is_available(self):
        app=ROOT.parent/'Akari/FoodArtworkClassification.json'
        if app.exists():
            self.assertEqual(app.read_bytes(),(ROOT/'artwork-classification.json').read_bytes())
            self.assertEqual((ROOT.parent/'AkariTests/FoodArtworkClassificationFixtures.json').read_bytes(),(ROOT/'classification-fixtures.json').read_bytes())
            ids={a['id'] for a in json.loads((ROOT.parent/'Akari/FluentFoodArtwork.json').read_text())['assets']}
            self.assertTrue(all(r['artworkID'] in ids for r in MANIFEST['rules']))

    def test_live_cheese_sample(self):
        sample=ROOT/'analysis/branded-sample-2026-09-06.json'
        if not sample.exists(): self.skipTest('Audit data is not required for deployment')
        successful=[p for p in json.loads(sample.read_text())['products'] if 'categories_tags' in p]
        self.assertEqual(len(successful),11)
        for p in successful:
            result=classify(p.get('product_name',''),p.get('brands'),p.get('generic_name'),p.get('categories_tags'))
            self.assertEqual(result['categoryID'],'cheese',p)
