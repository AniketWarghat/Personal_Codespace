from pathlib import Path
import io

import pandas as pd
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "survey_data.db"

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)


def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS survey_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                imported_at TEXT,
                data_json TEXT
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TEXT,
                status TEXT,
                rows_imported INTEGER,
                message TEXT
            )
        """))


def save_dataframe(df: pd.DataFrame, source_file: str):
    imported_at = pd.Timestamp.utcnow().isoformat()
    data_json = df.to_json(orient="records", date_format="iso")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM survey_data"))
        conn.execute(
            text("""
                INSERT INTO survey_data (source_file, imported_at, data_json)
                VALUES (:source_file, :imported_at, :data_json)
            """),
            {
                "source_file": source_file,
                "imported_at": imported_at,
                "data_json": data_json
            }
        )


def load_dataframe():
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT data_json, source_file, imported_at
            FROM survey_data
            ORDER BY id DESC
            LIMIT 1
        """)).fetchone()

    if not row:
        return None, None, None

    json_text = row[0]
    df = pd.read_json(io.StringIO(json_text))
    return df, row[1], row[2]


def log_sync(status: str, rows_imported: int = 0, message: str = ""):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO sync_runs (run_time, status, rows_imported, message)
                VALUES (:run_time, :status, :rows_imported, :message)
            """),
            {
                "run_time": pd.Timestamp.utcnow().isoformat(),
                "status": status,
                "rows_imported": rows_imported,
                "message": message
            }
        )


def get_recent_syncs(limit=5):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT run_time, status, rows_imported, message
                FROM sync_runs
                ORDER BY id DESC
                LIMIT :limit
            """),
            {"limit": limit}
        ).fetchall()

    return pd.DataFrame(rows, columns=["run_time", "status", "rows_imported", "message"])