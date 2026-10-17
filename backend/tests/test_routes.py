# backend/tests/test_routes.py
import sqlite3
import pytest
from fastapi.testclient import TestClient
import database

_TEST_DB = "file:testdb_routes?mode=memory&cache=shared&uri=true"
database.DB_PATH = _TEST_DB

# Keep a persistent connection open so the shared in-memory database
# is not destroyed between init_db() and the test queries.
_keeper = sqlite3.connect(_TEST_DB, uri=True, check_same_thread=False)

from database import init_db
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    from database import upsert_property, upsert_avg_price, upsert_cache_meta, get_connection
    # Clear tables first
    conn = get_connection()
    conn.execute("DELETE FROM properties")
    conn.execute("DELETE FROM avg_prices")
    conn.execute("DELETE FROM cache_meta")
    conn.commit()
    conn.close()
    upsert_property({
        "case_number": "ROUTE-001",
        "court": "台北地院",
        "district": "大安區",
        "address": "台北市大安區和平東路100號",
        "address_norm": "台北市大安區和平東路100號",
        "lat": 25.02, "lng": 121.53,
        "floor_price": 5_000_000,
        "area": 25.0, "property_type": "住宅",
        "auction_count": 1, "auction_date": "2026-04-01",
        "auction_url": "https://example.com/1",
    })
    upsert_avg_price("大安區", "住宅", 88.0, 100)
    upsert_cache_meta("大安區")


def test_get_properties_returns_200():
    resp = client.get("/api/properties?district=大安區")
    assert resp.status_code == 200
    data = resp.json()
    assert data["district"] == "大安區"
    assert data["total"] == 1
    assert len(data["properties"]) == 1


def test_get_properties_filter_min_price():
    resp = client.get("/api/properties?district=大安區&min_price=6000000")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_get_avg_prices_returns_200():
    resp = client.get("/api/avg-prices?district=大安區")
    assert resp.status_code == 200
    data = resp.json()
    assert data["district"] == "大安區"
    assert len(data["avg_prices"]) >= 1


def test_get_property_by_id():
    props = client.get("/api/properties?district=大安區").json()["properties"]
    pid = props[0]["id"]
    resp = client.get(f"/api/properties/{pid}")
    assert resp.status_code == 200
    assert resp.json()["case_number"] == "ROUTE-001"


def test_get_property_not_found():
    resp = client.get("/api/properties/99999")
    assert resp.status_code == 404


def test_run_refresh_does_not_raise_when_scrape_fails(monkeypatch, caplog):
    import logging
    import routes

    def _boom(district):
        raise RuntimeError("CAPTCHA fetch failed")

    monkeypatch.setattr(routes, "scrape_district", _boom)
    # Should log and return quietly instead of crashing the background task.
    with caplog.at_level(logging.ERROR, logger="routes"):
        routes._run_refresh("大安區")
    assert any("Refresh failed" in record.message for record in caplog.records)
