import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

DB_FILENAME = "database/gym_app.db"
OUTPUT_DIR = "schema_export"
OUTPUT_FILENAME = "database_schema.json"


def extract_schema_to_json(
    db_path: str = DB_FILENAME,
    output_dir: str = OUTPUT_DIR,
    output_file: str = OUTPUT_FILENAME
) -> None:
    """Extracts the full SQLite database schema and exports it to a JSON file in a folder."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Error: Database '{db_path}' not found. Run init_db.py first.")
        return

    # Create the target output folder if it doesn't exist
    out_folder = Path(output_dir)
    out_folder.mkdir(parents=True, exist_ok=True)
    out_path = out_folder / output_file

    schema_data = {
        "database_name": db_file.name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tables": {}
    }

    try:
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()

            # 1. Fetch all user-defined tables and their CREATE TABLE SQL statements
            cursor.execute("""
                SELECT name, sql 
                FROM sqlite_master 
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name;
            """)
            tables = cursor.fetchall()

            for table_name, create_sql in tables:
                # 2. Extract Columns using PRAGMA table_info
                cursor.execute(f"PRAGMA table_info('{table_name}');")
                columns = []
                for col in cursor.fetchall():
                    # col format: (cid, name, type, notnull, dflt_value, pk)
                    columns.append({
                        "column_id": col[0],
                        "name": col[1],
                        "type": col[2],
                        "not_null": bool(col[3]),
                        "default_value": col[4],
                        "is_primary_key": bool(col[5])
                    })

                # 3. Extract Foreign Keys using PRAGMA foreign_key_list
                cursor.execute(f"PRAGMA foreign_key_list('{table_name}');")
                foreign_keys = []
                for fk in cursor.fetchall():
                    # fk format: (id, seq, table, from, to, on_update, on_delete, match)
                    foreign_keys.append({
                        "column": fk[3],
                        "references_table": fk[2],
                        "references_column": fk[4],
                        "on_update": fk[5],
                        "on_delete": fk[6]
                    })

                # 4. Extract Indexes using PRAGMA index_list and PRAGMA index_info
                cursor.execute(f"PRAGMA index_list('{table_name}');")
                indexes = []
                for idx in cursor.fetchall():
                    # idx format: (seq, name, unique, origin, partial)
                    index_name = idx[1]
                    cursor.execute(f"PRAGMA index_info('{index_name}');")
                    indexed_columns = [info[2] for info in cursor.fetchall()]

                    indexes.append({
                        "name": index_name,
                        "is_unique": bool(idx[2]),
                        "origin": idx[3],  # 'c' = CREATE INDEX, 'u' = UNIQUE constraint, 'pk' = PRIMARY KEY
                        "columns": indexed_columns
                    })

                # 5. Get current row count for context
                cursor.execute(f"SELECT COUNT(*) FROM '{table_name}';")
                row_count = cursor.fetchone()[0]

                # Add table metadata to the schema dictionary
                schema_data["tables"][table_name] = {
                    "row_count": row_count,
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                    "indexes": indexes,
                    "ddl_sql": create_sql
                }

        # Write the dictionary to the JSON file
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(schema_data, f, indent=4, ensure_ascii=False)

        print(f"Schema successfully exported to: {out_path.resolve()}")
        print(f"Exported {len(schema_data['tables'])} tables: {', '.join(schema_data['tables'].keys())}")

    except sqlite3.Error as e:
        print(f"SQLite error occurred: {e}")
    except OSError as e:
        print(f"File system error occurred: {e}")


if __name__ == "__main__":
    extract_schema_to_json()