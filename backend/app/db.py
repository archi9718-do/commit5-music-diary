import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "moodwave.db"


def database_path() -> Path:
    return Path(os.environ.get("MOODWAVE_DB_PATH", str(DEFAULT_DB_PATH)))


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    con = connect()
    try:
        with con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL DEFAULT '',
                    predicted_emotion TEXT,
                    confirmed_emotion TEXT,
                    confidence TEXT,
                    probs_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS recommendations (
                    record_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    song_id TEXT NOT NULL,
                    brightness REAL NOT NULL,
                    energy REAL NOT NULL,
                    step TEXT NOT NULL,
                    PRIMARY KEY (record_id, position),
                    FOREIGN KEY (record_id) REFERENCES records (id)
                );
                """
            )
    finally:
        con.close()
