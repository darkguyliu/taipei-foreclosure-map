# backend/tests/test_database_schema.py
import sqlite3
import pytest
import database

_TEST_DB = "file:testdb_schema?mode=memory&cache=shared&uri=true"
database.DB_PATH = _TEST_DB

from database import init_db, get_connection

# Keep a persistent connection open so the shared in-memory database
# is not destroyed between init_db() and the assertion queries.
_keeper = sqlite3.connect(_TEST_DB, uri=True, check_same_thread=False)


def test_init_db_creates_tables():
    init_db()
    conn = get_connection()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    assert "properties" in tables
    assert "avg_prices" in tables
    assert "cache_meta" in tables
    conn.close()


def test_avg_prices_unique_constraint():
    init_db()
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO avg_prices(district, property_type, avg_price, sample_count) "
        "VALUES (?, ?, ?, ?)",
        ("大安區", "住宅", 88.0, 100),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO avg_prices(district, property_type, avg_price, sample_count) "
            "VALUES (?, ?, ?, ?)",
            ("大安區", "住宅", 90.0, 50),
        )
    # conn.commit() would auto-rollback after the IntegrityError anyway;
    # calling close() is sufficient here.
    conn.close()
