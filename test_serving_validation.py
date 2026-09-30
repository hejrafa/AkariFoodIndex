import unittest
from pathlib import Path
from serving_validation import accepts
from build_index import serving


class ServingValidationTests(unittest.TestCase):
    def test_wrong_food_serving_is_removed_from_the_index(self):
        self.assertEqual(serving(dict(product_name='Cevapcici, Rindfleisch',
            serving_quantity=28, serving_quantity_unit='g', serving_size='3 ONIONS (28 g)')),
            (None, None, None, None, None))

    def test_real_measures_and_matching_food_counts_are_preserved(self):
        for label, name, expected in [('3 ONIONS (28 g)', 'Zwiebeln', True),
                ('1 egg (50 g)', 'Egg, whole, raw', True), ('1 apple (120 g)', 'Birne', False),
                ('3 onions (28 g)', 'Cevapcici mit Zwiebeln', False),
                ('1 cup (150 g)', 'Rice', True), ('2 pieces (90 g)', 'Cevapcici', True)]:
            self.assertEqual(accepts(label, name), expected, (label, name))
        self.assertTrue(accepts('3 onions (28 g)', 'Original', 'Pearl onions'))

    def test_app_and_index_share_identity_rules(self):
        root = Path(__file__).resolve().parent
        app = root.parent / 'Akari/FoodServingIdentities.json'
        if app.exists():
            self.assertEqual(app.read_bytes(), (root / 'serving-identities.json').read_bytes())
