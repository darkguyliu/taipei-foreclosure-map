# backend/database.py
import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


def get_connection():
    # Use URI format when path starts with "file:" (for in-memory shared connections in tests)
    uri = DB_PATH.startswith("file:")
    conn = sqlite3.connect(DB_PATH, uri=uri, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if not uri:
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    # Use a plain connection for DDL — executescript() issues an implicit COMMIT
    # which bypasses the get_db() transaction; calling it directly is cleaner.
    conn = get_connection()
    conn.executescript("""
            CREATE TABLE IF NOT EXISTS properties (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                case_number   TEXT UNIQUE,
                court         TEXT,
                district      TEXT,
                address       TEXT,
                address_norm  TEXT,
                lat           REAL,
                lng           REAL,
                floor_price   INTEGER,
                area          REAL,
                property_type TEXT,
                auction_count INTEGER,
                auction_date  TEXT,
                auction_url   TEXT,
                created_at    TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at    TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS avg_prices (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                district      TEXT,
                property_type TEXT,
                avg_price     REAL,
                sample_count  INTEGER,
                updated_at    TEXT DEFAULT (datetime('now', 'localtime')),
                UNIQUE(district, property_type)
            );

            CREATE TABLE IF NOT EXISTS cache_meta (
                district           TEXT PRIMARY KEY,
                last_refreshed_at  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_properties_district
                ON properties(district);
            CREATE INDEX IF NOT EXISTS idx_properties_address_norm
                ON properties(address_norm);
        """)
    conn.close()
