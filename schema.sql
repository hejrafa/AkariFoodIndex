PRAGMA application_id = 1095451218;
PRAGMA user_version = 4;
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = OFF;
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

-- A family is the single item shown in search. Multiple barcodes and package
-- sizes remain available as SKUs underneath it instead of becoming duplicate
-- results.
CREATE TABLE family (
    id INTEGER PRIMARY KEY,
    family_key TEXT NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL,
    canonical_brand TEXT,
    normalized_name TEXT NOT NULL,
    normalized_brand TEXT NOT NULL,
    representative_sku_id INTEGER,
    variant_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sku (
    id INTEGER PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES family(id) ON DELETE CASCADE,
    barcode TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    brand TEXT,
    market TEXT NOT NULL,
    nutrition_basis TEXT NOT NULL CHECK (
        nutrition_basis IN ('per100Grams', 'per100Milliliters')
    ),
    serving_amount REAL,
    serving_unit TEXT,
    serving_grams REAL,
    serving_milliliters REAL,
    serving_label TEXT,
    image_url TEXT,
    nutri_score TEXT,
    nova_group INTEGER,
    nutrient_levels_json TEXT NOT NULL DEFAULT '{}',
    calories REAL NOT NULL,
    -- Sparse Akari-unit values (kcal, g, mg, or micrograms) keyed by
    -- NutrientKind raw value. Keeping calories scalar preserves cheap ranking
    -- and validation while this payload makes the product fully loggable.
    nutrients_json TEXT NOT NULL DEFAULT '{}',
    localized_names_json TEXT NOT NULL DEFAULT '{}',
    generic_name TEXT,
    localized_generic_names_json TEXT NOT NULL DEFAULT '{}',
    categories_json TEXT NOT NULL DEFAULT '[]',
    category_tags_json TEXT NOT NULL DEFAULT '[]',
    alcohol_classification TEXT NOT NULL DEFAULT 'unknown' CHECK (
        alcohol_classification IN ('alcoholic', 'nonAlcoholic', 'unknown')
    ),
    artwork_classification_json TEXT NOT NULL DEFAULT '{}',
    nutrient_count INTEGER NOT NULL,
    micronutrient_count INTEGER NOT NULL,
    completeness REAL,
    quality_score INTEGER NOT NULL,
    source_modified_at INTEGER,
    record_hash TEXT NOT NULL,
    validation_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX sku_family_index ON sku(family_id);
CREATE INDEX sku_barcode_index ON sku(barcode);
CREATE INDEX sku_quality_index ON sku(family_id, quality_score DESC);

-- FTS contains one row per family, but its document accumulates localized and
-- generic names, categories, tags, and compound aliases from every SKU.
-- Search therefore keeps broad identity recall without exposing duplicate
-- upstream package variants.
CREATE VIRTUAL TABLE family_search USING fts5(
    searchable,
    content = '',
    tokenize = 'unicode61 remove_diacritics 2'
);
