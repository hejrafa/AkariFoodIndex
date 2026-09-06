import json
import pathlib
import sqlite3
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from build_food_taxonomy import compile_taxonomy
from food_taxonomy import CATALOG, most_specific, search_names
from build_index import scaled_nutrients, validation_issues

class FoodQualityTests(unittest.TestCase):
    def test_taxonomy_rejects_disagreement_proxy_and_ambiguous_name(self):
        taxonomy={
            'en:cheeses':{'name':{'en':'Cheese'},'ciqual_proxy_food_code':{'en':'1'}},
            'en:edam':{'parents':['en:cheeses'],'name':{'en':'Edam','de':'Edamer'},'ciqual_food_code':{'en':'2'},'ciqual_food_name':{'fr':'Edam'}},
            'en:bad':{'ciqual_food_code':{'en':'2'},'ciqual_food_name':{'fr':'Cheddar'}},
        }
        rules={'version':3,'rules':[{'id':'cheese','tags':['en:cheeses'],'priority':60}]}
        result,report=compile_taxonomy(taxonomy,rules,{'ciqual:2':'Edam'})
        self.assertEqual(result['tags']['en:edam'],'cheese')
        self.assertEqual(set(result['referenceLinks']),{'en:edam'})
        self.assertEqual(report['rejectedReferenceLinks'],{'reference-name-disagrees':1})

    def test_specific_names_do_not_import_unrelated_parent_identity(self):
        self.assertEqual(most_specific(['en:cheeses','en:gouda']),['en:gouda'])
        self.assertTrue(any('gouda' in name.lower() for name in search_names(['en:gouda'])))
        self.assertNotIn('en:cheeses', CATALOG['referenceLinks'])
        self.assertNotIn('en:tomato-sauces-for-pizzas', CATALOG['referenceLinks'])

    def test_translations_and_reference_links_have_real_source_evidence(self):
        self.assertGreater(len(CATALOG['tags']),9000)
        self.assertGreater(len(CATALOG['referenceLinks']),1000)
        self.assertEqual(CATALOG['source']['url'],'https://static.openfoodfacts.org/data/taxonomies/categories.json')
        self.assertEqual(len(CATALOG['source']['sha256']),64)
        app=ROOT.parent/'Akari/FoodCategoryTaxonomy.json'
        if app.exists(): self.assertEqual(app.read_bytes(),(ROOT/'food-category-taxonomy.json').read_bytes())
        reference=ROOT.parent/'Akari/ReferenceFoods.sqlite'
        if reference.exists():
            db=sqlite3.connect(f'file:{reference}?mode=ro',uri=True)
            refs=dict(db.execute("select id,name from reference_food where source='ciqual'"));db.close()
            for link in CATALOG['referenceLinks'].values():
                self.assertEqual(refs[link['referenceCode']],link['referenceName'])

    def test_salt_is_converted_only_if_sodium_is_missing(self):
        self.assertEqual(scaled_nutrients({'salt_100g':1.8},'per100Grams')['sodium'],720)
        self.assertEqual(scaled_nutrients({'salt_100g':1.8,'sodium_100g':0},'per100Grams')['sodium'],0)

    def test_cross_field_and_impossible_quantities_are_flagged(self):
        flags=validation_issues({'calories':400,'fat':30,'carbs':60,'protein':20,
                                 'sugar':90,'saturatedFat':35,'sodium':150000})
        self.assertIn('macro-mass-exceeds-basis',flags)
        self.assertIn('sugar-exceeds-carbs',flags)
        self.assertIn('saturatedFat-exceeds-fat',flags)
        self.assertIn('invalid-sodium',flags)

class NutritionProvenanceTests(unittest.TestCase):
    def test_estimated_vitamins_never_become_reported_label_values(self):
        from normalize_off_nutrition import normalize_record
        product={'nutrition':{'input_sets':[
            {'source':'packaging','preparation':'as_sold','per':'100g','nutrients':{
                'energy-kcal':{'value':357,'value_computed':355,'unit':'kcal'},
                'proteins':{'value':13,'unit':'g'},'calcium':{'value':0,'unit':'mg'}}},
            {'source':'estimate','preparation':'as_sold','per':'100g','nutrients':{
                'vitamin-a':{'value':5.158125,'unit':'g'},'calcium':{'value':28,'unit':'mg'}}}],
            'aggregated_set':{'nutrients':{'vitamin-a':{'value':5.158125,'unit':'g','source':'estimate'}}}}}
        values=normalize_record(product)['nutriments']
        self.assertEqual(values['energy-kcal_100g'],357)
        self.assertEqual(values['calcium_100g'],0)
        self.assertNotIn('vitamin-a_100g',values)

    def test_serving_mass_and_vitamin_units_are_normalized_without_volume_guess(self):
        from normalize_off_nutrition import normalize_record
        product={'nutrition':{'input_sets':[{'source':'manufacturer','preparation':'as_sold',
            'per':'serving','per_quantity':20,'per_unit':'g','nutrients':{
                'energy-kcal':{'value':50,'unit':'kcal'},'proteins':{'value':5,'unit':'g'},
                'vitamin-b12':{'value':.24,'unit':'µg'},'vitamin-a':{'value':10,'unit':'% DV'}}}]}}
        result=normalize_record(product)
        self.assertEqual(result['nutrition_data_per'],'100g')
        self.assertEqual(result['nutriments']['energy-kcal_100g'],250)
        self.assertAlmostEqual(result['nutriments']['vitamin-b12_100g'],.0000012)
        self.assertNotIn('vitamin-a_100g',result['nutriments'])
        product['nutrition']['input_sets'][0]['per_unit']='ml'
        self.assertEqual(normalize_record(product)['nutrition_data_per'],'100ml')

    def test_prepared_estimated_and_legacy_nutrients_remain_separate(self):
        from normalize_off_nutrition import normalize_record
        product={'nutrition':{'input_sets':[{'source':'packaging','preparation':'prepared',
            'per':'100g','nutrients':{'energy-kcal':{'value':100,'unit':'kcal'}}}]},
            'nutriments':{'energy-kcal_100g':999}}
        self.assertEqual(normalize_record(product)['nutriments'],{})
        legacy={'nutriments':{'energy-kcal_100g':100},'nutriments_estimated':{'vitamin-a_100g':99}}
        self.assertEqual(normalize_record(legacy)['nutriments'],{'energy-kcal_100g':100})

class ReleaseProvenanceTests(unittest.TestCase):
    def test_production_cli_rejects_flat_csv(self):
        import subprocess,tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);source=root/'products.csv';source.write_text('code\tproduct_name\n')
            result=subprocess.run([sys.executable,str(ROOT/'build_index.py'),'--off-export',str(source),
                '--market','DE=en:germany','--output-dir',str(root/'dist')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('CSV mixes reported and estimated',result.stderr)

    def test_release_gate_rejects_unverified_provenance_even_with_valid_hash(self):
        import hashlib,subprocess,tempfile
        from verify_release import verify
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);source=root/'products.jsonl';dist=root/'dist'
            source.write_text(json.dumps({'code':'4002468181006','product_name':'Test food','countries_tags':['en:germany'],
                'nutriments':{'energy-kcal_100g':170,'proteins_100g':10,'fat_100g':10,'carbohydrates_100g':10}})+'\n')
            subprocess.run([sys.executable,str(ROOT/'build_index.py'),'--off-export',str(source),
                '--market','DE=en:germany','--output-dir',str(dist)],check=True,capture_output=True)
            self.assertEqual(verify(dist)['schemaVersion'],4)
            path=dist/'akari-food-de.sqlite';db=sqlite3.connect(path)
            db.execute("UPDATE metadata SET value='unverified-flat-csv' WHERE key='nutrition_provenance'");db.commit();db.close()
            manifest=json.loads((dist/'manifest.json').read_text());asset=manifest['markets']['DE']
            asset['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();asset['bytes']=path.stat().st_size
            (dist/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'unverified/CSV'):verify(dist)
