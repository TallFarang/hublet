"""Food database schema and shared domain constants."""

DB_FILENAME = "food.db"
STATUSES = {"eaten", "uncertain", "excluded"}
CONFIDENCES = {"exact", "high", "medium", "low", "unknown"}

MIGRATIONS = (
    """
    CREATE TABLE nutrition (
        id TEXT PRIMARY KEY,
        restaurant TEXT NOT NULL,
        category TEXT,
        item TEXT NOT NULL,
        calories REAL NOT NULL CHECK (calories >= 0),
        calories_min REAL CHECK (calories_min IS NULL OR calories_min >= 0),
        calories_max REAL CHECK (calories_max IS NULL OR calories_max >= 0),
        protein_g REAL NOT NULL CHECK (protein_g >= 0),
        carbs_g REAL NOT NULL CHECK (carbs_g >= 0),
        fat_g REAL NOT NULL CHECK (fat_g >= 0),
        portion_basis TEXT NOT NULL,
        source TEXT NOT NULL,
        confidence TEXT NOT NULL
            CHECK (confidence IN ('exact', 'high', 'medium', 'low', 'unknown')),
        review_date TEXT,
        evidence_class TEXT NOT NULL CHECK (length(trim(evidence_class)) > 0),
        evidence_basis TEXT,
        updated_at TEXT NOT NULL,
        CHECK (
            (calories_min IS NULL AND calories_max IS NULL)
            OR
            (calories_min IS NOT NULL AND calories_max IS NOT NULL
             AND calories_min <= calories AND calories <= calories_max)
        )
    );
    CREATE INDEX nutrition_match ON nutrition(restaurant, item, portion_basis);

    CREATE TABLE records (
        id TEXT PRIMARY KEY,
        receipt_id TEXT,
        order_id TEXT,
        email_message_id TEXT,
        receipt_line TEXT,
        purchase_timestamp_utc TEXT,
        purchase_date_local TEXT,
        consumption_timestamp_utc TEXT,
        consumption_date_local TEXT,
        meal_slot TEXT,
        restaurant TEXT NOT NULL,
        item TEXT NOT NULL,
        quantity REAL NOT NULL DEFAULT 1 CHECK (quantity > 0),
        portion_text TEXT,
        status TEXT NOT NULL DEFAULT 'uncertain'
            CHECK (status IN ('eaten', 'uncertain', 'excluded')),
        nutrition_id TEXT REFERENCES nutrition(id),
        nutrition_multiplier REAL NOT NULL DEFAULT 1 CHECK (nutrition_multiplier > 0),
        notes TEXT,
        apple_health_reference TEXT,
        apple_health_sample_uuid TEXT,
        apple_health_synced_at TEXT,
        updated_at TEXT NOT NULL,
        update_reason TEXT NOT NULL CHECK (length(trim(update_reason)) > 0),
        ingest_fingerprint TEXT,
        CHECK (purchase_timestamp_utc IS NULL OR purchase_date_local IS NOT NULL),
        CHECK (consumption_timestamp_utc IS NULL OR consumption_date_local IS NOT NULL)
    );
    CREATE INDEX records_order_id ON records(order_id);
    CREATE INDEX records_email_message_id ON records(email_message_id);
    CREATE INDEX records_consumption_date ON records(consumption_date_local, status);
    CREATE INDEX records_purchase_date ON records(purchase_date_local);
    CREATE INDEX records_nutrition_id ON records(nutrition_id);
    """,
)
