# Analysis

What remains here is the one file a test reads:

- `branded-sample-2026-09-06.json`: a sample of branded Open Food Facts rows
  that `FoodIndex/test_classification.py` classifies, so a rule change that
  moves a branded product's artwork fails a test.

The full catalogue quality audit of 6 September 2026 (the nine-market coverage
counts, the CSV diagnostic that rejected the flat export, the taxonomy and
artwork coverage audits, the Babybel and research source trails and the
legacy schema-1 classification audit) lived in this folder until 3 November
2026. Its findings are in git history (`git log -- FoodIndex/analysis`); the
rules it led to are the ones `classify_artwork.py`, `build_index.py` and
`verify_release.py` enforce today, and the current catalogue's numbers are in
`FoodIndex/health/`.
