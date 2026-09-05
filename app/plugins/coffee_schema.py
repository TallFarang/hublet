"""Coffee database schema and fixed brewing vocabulary."""

DB_FILENAME = "coffee.db"
DEFAULT_GRINDER = "Lagom Mini"
METHODS = {"v60", "aeropress", "french_press", "espresso"}

MIGRATIONS = (
    """
    CREATE TABLE beans (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        roaster TEXT,
        roast_date TEXT,
        origin TEXT,
        process TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'archived')),
        notes TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE shots (
        id TEXT PRIMARY KEY,
        bean_id TEXT NOT NULL REFERENCES beans(id),
        dose_g REAL NOT NULL CHECK (dose_g > 0),
        yield_g REAL NOT NULL CHECK (yield_g > 0),
        time_s REAL NOT NULL CHECK (time_s > 0),
        grind_setting TEXT NOT NULL,
        grinder TEXT,
        temperature_c REAL,
        rating INTEGER CHECK (rating BETWEEN 1 AND 5),
        taste_tags_json TEXT NOT NULL DEFAULT '[]',
        notes TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    DROP TABLE shots;
    DROP TABLE beans;

    CREATE TABLE bags (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        roaster TEXT NOT NULL CHECK (length(trim(roaster)) > 0),
        roast_date TEXT,
        roast_level TEXT,
        origin TEXT,
        process TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'archived')),
        notes TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX bags_identity ON bags(roaster COLLATE NOCASE, name COLLATE NOCASE);

    CREATE TABLE brews (
        id TEXT PRIMARY KEY,
        bag_id TEXT NOT NULL REFERENCES bags(id),
        method TEXT NOT NULL CHECK (
            method IN ('v60', 'aeropress', 'french_press', 'espresso')
        ),
        dose_g REAL NOT NULL CHECK (dose_g > 0),
        water_g REAL CHECK (water_g > 0),
        yield_g REAL CHECK (yield_g > 0),
        time_s REAL CHECK (time_s > 0),
        grind_setting TEXT NOT NULL CHECK (length(trim(grind_setting)) > 0),
        grinder TEXT NOT NULL CHECK (length(trim(grinder)) > 0),
        temperature_c REAL CHECK (temperature_c > 0),
        bypass_water_g REAL CHECK (bypass_water_g > 0),
        rating INTEGER CHECK (rating BETWEEN 1 AND 5),
        taste_notes TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        CHECK (
            (method = 'espresso' AND water_g IS NULL AND yield_g IS NOT NULL)
            OR (method != 'espresso' AND water_g IS NOT NULL AND yield_g IS NULL)
        ),
        CHECK (method != 'espresso' OR bypass_water_g IS NULL),
        CHECK (rating IS NOT NULL OR length(trim(coalesce(taste_notes, ''))) > 0)
    );
    CREATE INDEX brews_history ON brews(bag_id, created_at DESC);
    """,
)
