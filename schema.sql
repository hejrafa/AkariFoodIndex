PRAGMA application_id = 1095451218;
PRAGMA user_version = 1;
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
    serving_grams REAL,
    serving_label TEXT,
    image_url TEXT,
    nutri_score TEXT,
    nova_group INTEGER,
    nutrient_levels_json TEXT NOT NULL DEFAULT '{}',
    calories REAL NOT NULL,
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

-- FTS contains one row per canonical family. Search therefore cannot expose
-- thirty upstream copies of the same named product.
CREATE VIRTUAL TABLE family_search USING fts5(
    searchable,
    content = '',
    tokenize = 'unicode61 remove_diacritics 2'
);
