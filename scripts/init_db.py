from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Config


def run_script(cursor: sqlite3.Cursor, script_path: Path) -> None:
    sql = script_path.read_text(encoding="utf-8")
    cursor.executescript(sql)


def init_database() -> None:
    create_sql = PROJECT_ROOT / "scripts" / "001_create_tables.sql"
    seed_sql = PROJECT_ROOT / "scripts" / "002_seed_data.sql"

    conn = sqlite3.connect(Config.SQLITE_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        run_script(cursor, create_sql)
        run_script(cursor, seed_sql)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_database()
    print(f"SQLite DB initialized: {Config.SQLITE_PATH}")
