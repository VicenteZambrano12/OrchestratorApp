import sqlite3
from pathlib import Path

DB_FILENAME = "database/gym_app.db"

SCHEMA_SQL = """
-- Enable Foreign Key enforcement in SQLite
PRAGMA foreign_keys = ON;

-- ==========================================
-- 1. DIMENSION: Exercises (The Encyclopedia)
-- ==========================================
CREATE TABLE IF NOT EXISTS dim_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    instructions TEXT NOT NULL,
    
    -- Categorization & Filtering
    primary_muscle TEXT NOT NULL CHECK(primary_muscle IN (
        'chest', 'back', 'shoulders', 'quads', 'hamstrings', 
        'glutes', 'calves', 'triceps', 'biceps', 'forearms', 'core'
    )),
    secondary_muscles TEXT, -- JSON array format, e.g., '["triceps", "shoulders"]'
    pattern TEXT NOT NULL CHECK(pattern IN (
        'push', 'pull', 'legs', 'core', 'cardio'
    )),
    equipment TEXT NOT NULL CHECK(equipment IN (
        'barbell', 'dumbbell', 'machine', 'cable', 
        'bodyweight', 'kettlebell', 'band', 'smith_machine', 'other', 'none'
    )),
    
    -- Exercise Characteristics
    mechanic TEXT NOT NULL CHECK(mechanic IN ('compound', 'isolation')),
    level TEXT NOT NULL CHECK(level IN ('beginner', 'intermediate', 'advanced')),
    intensity TEXT NOT NULL CHECK(intensity IN ('low', 'medium', 'high')),
    
    -- App Logic & Workout Tracking
    tracking_type TEXT NOT NULL DEFAULT 'weight_reps' CHECK(tracking_type IN (
        'weight_reps', 'reps_only', 'time', 'distance_time', 'weight_time'
    )),
    is_unilateral INTEGER NOT NULL DEFAULT 0 CHECK(is_unilateral IN (0, 1)),
    
    -- Visual Assets & Media
    media_url TEXT,
    icon_url TEXT,
    anatomy_diagram_url TEXT,
    
    -- Metadata
    is_custom INTEGER NOT NULL DEFAULT 0 CHECK(is_custom IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 2. DIMENSION: Users
-- ==========================================
CREATE TABLE IF NOT EXISTS dim_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    weight_unit TEXT NOT NULL DEFAULT 'kg' CHECK(weight_unit IN ('kg', 'lbs')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 3. DIMENSION: Routines (Routine Maker/Updater)
-- ==========================================
CREATE TABLE IF NOT EXISTS dim_routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES dim_users(id) ON DELETE CASCADE
);

-- ==========================================
-- 4. FACT TABLE: Workout Sets & Routine Templates
-- ==========================================
CREATE TABLE IF NOT EXISTS fact_workout_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Foreign Keys pointing to Dimensions
    user_id INTEGER NOT NULL,
    routine_id INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    
    -- Session & Ordering Identifiers
    -- NULL = Routine Template | NOT NULL = Logged Historical Workout
    training_id TEXT,
    exercise_order INTEGER NOT NULL DEFAULT 1,
    set_number INTEGER NOT NULL DEFAULT 1,
    
    -- Fact Metrics
    reps INTEGER,
    weight REAL,
    duration_seconds INTEGER,
    distance_meters REAL,
    rpe REAL CHECK(rpe BETWEEN 1 AND 10),
    
    -- Timestamps
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES dim_users(id) ON DELETE CASCADE,
    FOREIGN KEY (routine_id) REFERENCES dim_routines(id) ON DELETE CASCADE,
    FOREIGN KEY (exercise_id) REFERENCES dim_exercises(id) ON DELETE RESTRICT
);

-- ==========================================
-- 5. INDEXES FOR FAST QUERIES
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_exercises_primary_muscle ON dim_exercises(primary_muscle);
CREATE INDEX IF NOT EXISTS idx_exercises_equipment ON dim_exercises(equipment);
CREATE INDEX IF NOT EXISTS idx_exercises_pattern ON dim_exercises(pattern);

CREATE INDEX IF NOT EXISTS idx_fact_user_training ON fact_workout_sets(user_id, training_id);
CREATE INDEX IF NOT EXISTS idx_fact_routine_template ON fact_workout_sets(routine_id, training_id);
CREATE INDEX IF NOT EXISTS idx_fact_exercise_history ON fact_workout_sets(user_id, exercise_id, created_at);
"""

def create_empty_database(db_path: str = DB_FILENAME) -> None:
    """Creates an empty SQLite database with the Star Schema."""
    path = Path(db_path)
    
    try:
        # Connect to SQLite (creates the file if it doesn't exist)
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            
            # Execute the entire schema script at once
            cursor.executescript(SCHEMA_SQL)
            conn.commit()
            
            # Verify tables were created
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = [row[0] for row in cursor.fetchall()]
            
            print(f"Database created successfully at: {path.resolve()}")
            print(f"Created tables: {', '.join(tables)}")
            
    except sqlite3.Error as e:
        print(f"SQLite error occurred: {e}")

if __name__ == "__main__":
    create_empty_database()