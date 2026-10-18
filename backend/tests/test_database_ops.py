# backend/tests/test_database_ops.py
import pytest
import sqlite3
import database

# Distinct named DB from test_database_schema.py to avoid cross-module state sharing.
_TEST_DB = "file:testdb_ops?mode=memory&cache=shared&uri=true"
database.DB_PATH = _TEST_DB

from database import (
    init_db, get_connection, upsert_property, upsert_avg_price, upsert_cache_meta,
    get_properties, get_avg_prices, get_geocode_cache,
)

# Keep a persistent connection open so the shared in-memory database
# is not destroyed between init_db() and the test queries.
_keeper = sqlite3.connect(_TEST_DB, uri=True, check_same_thread=False)


@pytest.fixture(autouse=True)
def fresh_db():
    """Re-initialize schema and clear data before each test to isolate state."""
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM properties")
    conn.execute("DELETE FROM avg_prices")
    conn.execute("DELETE FROM cache_meta")
    conn.commit()
    conn.close()
    yield


def test_upsert_property_inserts():
    prop = {
        "case_number": "TEST-001",
        "court": "台北地院",
        "district": "大安區",
        "address": "台北市大安區和平東路100號3樓",
        "address_norm": "台北市大安區和平東路100號",
        "lat": 25.02,
        "lng": 121.53,
        "floor_price": 5000000,
        "area": 25.0,
        "property_type": "住宅",
        "auction_count": 1,
        "auction_date": "2026-04-01",
        "auction_url": "https://example.com/1",
    }
    upsert_property(prop)
    results = get_properties("大安區")
    assert len(results) == 1
    assert results[0]["case_number"] == "TEST-001"


def test_upsert_property_updates_on_duplicate():
    prop = {
        "case_number": "TEST-002",
        "court": "台北地院",
        "district": "信義區",
        "address": "台北市信義區信義路五段100號",
        "address_norm": "台北市信義區信義路五段100號",
        "lat": 25.03, "lng": 121.56,
        "floor_price": 8000000,
        "area": 30.0, "property_type": "住宅",
        "auction_count": 1, "auction_date": "2026-04-01",
        "auction_url": "https://example.com/2",
    }
    upsert_property(prop)
    prop["floor_price"] = 7500000  # updated
    upsert_property(prop)
    results = get_properties("信義區")
    assert len(results) == 1
    assert results[0]["floor_price"] == 7500000


def test_upsert_avg_price():
    upsert_avg_price("大安區", "住宅", 88.0, 100)
    upsert_avg_price("大安區", "住宅", 90.0, 110)  # should update
    prices = get_avg_prices("大安區")
    property_price = next(p for p in prices if p["property_type"] == "住宅")
    assert property_price["avg_price"] == 90.0


def test_get_geocode_cache_maps_address_norm_to_coords():
    upsert_property({
        "case_number": "GEO-001", "court": "台北地院", "district": "大安區",
        "address": "台北市大安區仁愛路一段1號",
        "address_norm": "台北市大安區仁愛路一段1號",
        "lat": 25.03, "lng": 121.54,
        "floor_price": 1_000_000, "area": 10.0, "property_type": "住宅",
        "auction_count": 1, "auction_date": "2026-04-01", "auction_url": "",
    })
    upsert_property({
        "case_number": "GEO-002", "court": "台北地院", "district": "大安區",
        "address": "台北市大安區仁愛路二段2號",
        "address_norm": "台北市大安區仁愛路二段2號",
        "lat": None, "lng": None,  # never geocoded — should be excluded
        "floor_price": 2_000_000, "area": 20.0, "property_type": "住宅",
        "auction_count": 1, "auction_date": "2026-04-01", "auction_url": "",
    })
    cache = get_geocode_cache([
        "台北市大安區仁愛路一段1號", "台北市大安區仁愛路二段2號",
    ])
    assert cache["台北市大安區仁愛路一段1號"] == (25.03, 121.54)
    assert "台北市大安區仁愛路二段2號" not in cache


def test_get_geocode_cache_scoped_to_requested_addresses():
    # A geocoded address not included in the requested list must not come
    # back — the cache is scoped to this batch, not the whole table.
    upsert_property({
        "case_number": "GEO-003", "court": "台北地院", "district": "信義區",
        "address": "台北市信義區松仁路1號",
        "address_norm": "台北市信義區松仁路1號",
        "lat": 25.04, "lng": 121.57,
        "floor_price": 3_000_000, "area": 15.0, "property_type": "住宅",
        "auction_count": 1, "auction_date": "2026-04-01", "auction_url": "",
    })
    cache = get_geocode_cache(["台北市大安區仁愛路一段1號"])  # unrelated address
    assert cache == {}


def test_get_geocode_cache_empty_input_returns_empty_dict():
    assert get_geocode_cache([]) == {}


def test_get_properties_filter_by_price():
    for i, price in enumerate([3_000_000, 8_000_000, 15_000_000]):
        upsert_property({
            "case_number": f"FILTER-{i}",
            "court": "台北地院", "district": "中山區",
            "address": f"台北市中山區南京東路{i}號",
            "address_norm": f"台北市中山區南京東路{i}號",
            "lat": 25.05, "lng": 121.52,
            "floor_price": price, "area": 20.0,
            "property_type": "住宅", "auction_count": 1,
            "auction_date": "2026-04-01", "auction_url": "",
        })
    results = get_properties("中山區", min_price=5_000_000, max_price=10_000_000)
    assert len(results) == 1
    assert results[0]["floor_price"] == 8_000_000
