"""The complete current-state schema for Health."""

DB_FILENAME = "health.db"

MAPPINGS = {
    "HKQuantityTypeIdentifierVO2Max": ("vo2_max", "ml/(kg*min)"),
    "HKQuantityTypeIdentifierBodyMass": ("body_weight_kg", "kg"),
    "HKQuantityTypeIdentifierRestingHeartRate": ("resting_heart_rate", "count/min"),
    "HKWorkoutTypeIdentifier": ("workouts_completed", "workouts"),
}

MIGRATIONS = (
    """
    CREATE TABLE days (
        export_date TEXT PRIMARY KEY,
        revision INTEGER NOT NULL,
        relative_path TEXT NOT NULL,
        content_digest TEXT NOT NULL,
        file_digest TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        timezone TEXT NOT NULL,
        period_start TEXT NOT NULL,
        period_end TEXT NOT NULL
    );
    CREATE TABLE types (
        export_date TEXT NOT NULL REFERENCES days(export_date) ON DELETE CASCADE,
        type TEXT NOT NULL,
        kind TEXT,
        record_count INTEGER,
        PRIMARY KEY (export_date, type)
    );
    CREATE TABLE records (
        id TEXT PRIMARY KEY,
        uuid TEXT UNIQUE,
        type TEXT NOT NULL,
        kind TEXT NOT NULL,
        local_date TEXT NOT NULL,
        start_at TEXT,
        end_at TEXT,
        value_json TEXT,
        unit TEXT,
        normalized_value REAL,
        normalized_unit TEXT,
        duration_seconds REAL,
        activity_type TEXT,
        raw_json TEXT NOT NULL,
        source_dates_json TEXT NOT NULL
    );
    CREATE INDEX records_type_date ON records(type, local_date, start_at);
    CREATE TABLE sync_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        last_attempt TEXT,
        last_success TEXT,
        status TEXT NOT NULL,
        error TEXT,
        dataset_digest TEXT,
        latest_export_date TEXT,
        timezone TEXT
    );
    INSERT INTO sync_state (id, status) VALUES (1, 'never_synced');
    """,
)
