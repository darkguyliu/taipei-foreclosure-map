# backend/database.py
import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, List, Dict, Iterable, Tuple

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
    conn.commit()
    conn.close()


def upsert_property(prop: Dict) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO properties
                (case_number, court, district, address, address_norm,
                 lat, lng, floor_price, area, property_type,
                 auction_count, auction_date, auction_url, updated_at)
            VALUES
                (:case_number, :court, :district, :address, :address_norm,
                 :lat, :lng, :floor_price, :area, :property_type,
                 :auction_count, :auction_date, :auction_url,
                 strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime'))
            ON CONFLICT(case_number) DO UPDATE SET
                court=excluded.court,
                address=excluded.address,
                address_norm=excluded.address_norm,
                lat=excluded.lat, lng=excluded.lng,
                floor_price=excluded.floor_price, area=excluded.area,
                property_type=excluded.property_type,
                auction_count=excluded.auction_count,
                auction_date=excluded.auction_date,
                auction_url=excluded.auction_url,
                updated_at=excluded.updated_at
        """, prop)


def upsert_avg_price(district: str, property_type: str, avg_price: float, sample_count: int) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO avg_prices(district, property_type, avg_price, sample_count, updated_at)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(district, property_type) DO UPDATE SET
                avg_price=excluded.avg_price,
                sample_count=excluded.sample_count,
                updated_at=excluded.updated_at
        """, (district, property_type, avg_price, sample_count))


def upsert_cache_meta(district: str) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO cache_meta(district, last_refreshed_at)
            VALUES (?, datetime('now', 'localtime'))
            ON CONFLICT(district) DO UPDATE SET
                last_refreshed_at=excluded.last_refreshed_at
        """, (district,))


_GEOCODE_CACHE_QUERY_CHUNK = 500  # stay well under SQLite's variable-count limit


def get_geocode_cache(address_norms: Iterable[Optional[str]]) -> Dict[str, Tuple[float, float]]:
    """Map each of the given address_norm values to its (lat, lng) where
    already geocoded, via bulk lookups scoped to this batch instead of one
    query per row (or loading every district's history). None entries
    (e.g. an address that failed to normalize) are ignored."""
    distinct = list({a for a in address_norms if a})
    if not distinct:
        return {}
    cache: Dict[str, Tuple[float, float]] = {}
    with get_db() as conn:
        for i in range(0, len(distinct), _GEOCODE_CACHE_QUERY_CHUNK):
            chunk = distinct[i:i + _GEOCODE_CACHE_QUERY_CHUNK]
            placeholders = ",".join("?" * len(chunk))
            # ORDER BY + dict construction below: if an address_norm has
            # multiple rows with different coordinates, the most recently
            # updated one wins deterministically. updated_at is written
            # with millisecond precision (see upsert_property) specifically
            # so two rows can't tie here — id can't substitute as a
            # tiebreaker since ON CONFLICT DO UPDATE leaves a row's id
            # unchanged, so it doesn't track write recency.
            rows = conn.execute(
                f"SELECT address_norm, lat, lng FROM properties "
                f"WHERE lat IS NOT NULL AND address_norm IN ({placeholders}) "
                f"ORDER BY updated_at ASC",
                chunk,
            ).fetchall()
            cache.update((row["address_norm"], (row["lat"], row["lng"])) for row in rows)
    return cache


def get_properties(
    district: str,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    auction_count: Optional[int] = None,
    property_type: Optional[str] = None,
) -> List[Dict]:
    query = "SELECT * FROM properties WHERE district = ? AND lat IS NOT NULL"
    params: List = [district]
    if min_price is not None:
        query += " AND floor_price >= ?"
        params.append(min_price)
    if max_price is not None:
        query += " AND floor_price <= ?"
        params.append(max_price)
    if auction_count is not None:
        if auction_count >= 3:
            query += " AND auction_count >= ?"
        else:
            query += " AND auction_count = ?"
        params.append(auction_count)
    if property_type is not None and property_type != "all":
        query += " AND property_type = ?"
        params.append(property_type)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_avg_prices(district: str) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM avg_prices WHERE district = ?", (district,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_cache_meta(district: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cache_meta WHERE district = ?", (district,)
        ).fetchone()
    return dict(row) if row else None


def get_property_by_id(property_id: int) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM properties WHERE id = ?", (property_id,)
        ).fetchone()
    return dict(row) if row else None
