# backend/tests/test_routes.py
import logging
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient
import database

_TEST_DB = "file:testdb_routes?mode=memory&cache=shared&uri=true"
database.DB_PATH = _TEST_DB

# Keep a persistent connection open so the shared in-memory database
# is not destroyed between init_db() and the test queries.
_keeper = sqlite3.connect(_TEST_DB, uri=True, check_same_thread=False)

# Imported after DB_PATH is overridden above, matching this file's other
# database-touching imports.
import routes
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
    # Both are process-local state, not DB state, so they'd otherwise leak
    # across tests (e.g. a 429 from one test's throttle check firing in a
    # later, unrelated test for the same district).
    routes._last_attempt.clear()
    routes._refreshing.clear()
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


def test_refresh_rejects_unknown_district():
    # district is caller-supplied; without this check an arbitrary string
    # would still get a cache_meta row written for it (scrape_district
    # returns [] for it, which otherwise passes the "something refreshed"
    # check in _run_refresh).
    resp = client.post("/api/refresh?district=不存在區")
    assert resp.status_code == 400


def test_refresh_rejects_recently_refreshed_district():
    # Without this check, a POST /refresh triggers a real scrape plus paid
    # geocoding calls with no limit on how often a caller can hit it.
    routes._last_attempt["大安區"] = time.monotonic()
    resp = client.post("/api/refresh?district=大安區")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_refresh_throttles_even_after_a_failed_attempt(monkeypatch):
    # The throttle is keyed off _last_attempt (set when a request is
    # accepted), not cache_meta.last_refreshed_at (only set on a
    # *successful* refresh) — otherwise a district whose scrape keeps
    # failing would never actually be throttled.
    def _boom(district):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "scrape_district", _boom)

    first = client.post("/api/refresh?district=信義區")
    assert first.status_code == 200

    second = client.post("/api/refresh?district=信義區")
    assert second.status_code == 429


def test_refresh_rejects_when_already_in_progress():
    # A district already mid-refresh (tracked in-process, not via DB) must
    # be rejected too — otherwise two concurrent refreshes for the same
    # district each load their own geocode_cache snapshot and can both pay
    # to geocode the same new address.
    routes._refreshing["士林區"] = time.monotonic()
    try:
        resp = client.post("/api/refresh?district=士林區")
        assert resp.status_code == 409  # resource conflict, not a rate limit
        assert "Retry-After" in resp.headers
    finally:
        routes._refreshing.pop("士林區", None)


def test_refresh_allows_retry_once_in_progress_entry_is_stale(monkeypatch):
    # An entry older than MAX_REFRESH_DURATION_SECONDS means the
    # BackgroundTask likely never actually ran within this process — it
    # must not block this district forever.
    monkeypatch.setattr(routes, "scrape_district", lambda district: [])
    monkeypatch.setattr(routes, "fetch_avg_prices", lambda district: [])

    routes._refreshing["北投區"] = time.monotonic() - routes.MAX_REFRESH_DURATION_SECONDS - 1

    resp = client.post("/api/refresh?district=北投區")
    assert resp.status_code == 200


def test_run_refresh_guarded_does_not_clobber_a_newer_entry(monkeypatch):
    # If a stale call's _refreshing entry has already been replaced by a
    # newer request's attempt (this one went stale and a second request
    # started), the stale call's cleanup must not delete that newer entry
    # — otherwise a third request could start concurrently with the
    # second, defeating the whole point of the guard.
    monkeypatch.setattr(routes, "scrape_district", lambda district: [])
    monkeypatch.setattr(routes, "fetch_avg_prices", lambda district: [])

    stale_started_at = time.monotonic() - routes.MAX_REFRESH_DURATION_SECONDS - 100
    routes._refreshing["內湖區"] = time.monotonic()  # a newer, legit in-progress entry

    routes._run_refresh_guarded("內湖區", stale_started_at)

    assert "內湖區" in routes._refreshing


def test_refresh_starts_for_district_without_recent_cache_meta(monkeypatch):
    # 信義區 has no cache_meta row from the fixture, so it isn't blocked by
    # the recency check or the in-progress guard. scrape_district is
    # monkeypatched so this doesn't hit the real network.
    monkeypatch.setattr(routes, "scrape_district", lambda district: [])
    monkeypatch.setattr(routes, "fetch_avg_prices", lambda district: [])

    resp = client.post("/api/refresh?district=信義區")

    assert resp.status_code == 200
    assert resp.json() == {"status": "started", "district": "信義區"}
    # TestClient runs BackgroundTasks synchronously, so by the time the
    # response above is returned, _run_refresh_guarded's `finally` should
    # have already released the in-progress guard.
    assert "信義區" not in routes._refreshing


def test_run_refresh_partial_scrape_persists_rows_but_skips_cache_meta(monkeypatch, caplog):
    rows = [{
        "case_number": "PARTIAL-001", "court": "台北地院", "district": "大安區",
        "address": "台北市大安區仁愛路一段1號", "floor_price": 1_000_000,
        "area": 10.0, "property_type": "住宅", "auction_count": 1,
        "auction_date": "2026-05-01", "auction_url": "",
    }]

    def _raise_partial(district):
        raise routes.PartialScrapeError(rows)

    monkeypatch.setattr(routes, "scrape_district", _raise_partial)
    monkeypatch.setattr(routes, "fetch_avg_prices", lambda district: [])
    monkeypatch.setattr(routes, "GOOGLE_API_KEY", "")

    cache_meta_calls = []
    monkeypatch.setattr(
        routes, "upsert_cache_meta", lambda district: cache_meta_calls.append(district)
    )

    with caplog.at_level(logging.WARNING, logger="routes"):
        routes._run_refresh("大安區")

    assert cache_meta_calls == []
    assert any("Partial scrape" in record.message for record in caplog.records)

    conn = database.get_connection()
    case_numbers = {
        row["case_number"]
        for row in conn.execute("SELECT case_number FROM properties").fetchall()
    }
    conn.close()
    assert "PARTIAL-001" in case_numbers  # still persisted despite being partial


def test_run_refresh_survives_geocode_cache_failure(monkeypatch, caplog):
    rows = [{
        "case_number": "CACHEFAIL-001", "court": "台北地院", "district": "大安區",
        "address": "台北市大安區仁愛路一段1號", "floor_price": 1_000_000,
        "area": 10.0, "property_type": "住宅", "auction_count": 1,
        "auction_date": "2026-05-01", "auction_url": "",
    }]
    monkeypatch.setattr(routes, "scrape_district", lambda district: rows)
    monkeypatch.setattr(routes, "fetch_avg_prices", lambda district: [])
    monkeypatch.setattr(routes, "GOOGLE_API_KEY", "")

    def _boom(address_norms):
        raise RuntimeError("DB locked")

    monkeypatch.setattr(routes, "get_geocode_cache", _boom)

    # A broken geocode cache lookup must not abort the whole refresh (this
    # file's own design rule: a BackgroundTask must never fail silently,
    # nor should one failed step take down everything after it).
    with caplog.at_level(logging.ERROR, logger="routes"):
        routes._run_refresh("大安區")

    assert any("Failed to load geocode cache" in record.message for record in caplog.records)

    conn = database.get_connection()
    case_numbers = {
        row["case_number"]
        for row in conn.execute("SELECT case_number FROM properties").fetchall()
    }
    conn.close()
    assert "CACHEFAIL-001" in case_numbers  # still persisted, just without a cache hit


def test_run_refresh_does_not_raise_when_scrape_fails(monkeypatch, caplog):
    def _boom(district):
        raise RuntimeError("CAPTCHA fetch failed")

    monkeypatch.setattr(routes, "scrape_district", _boom)
    # Should log and return quietly instead of crashing the background task.
    with caplog.at_level(logging.ERROR, logger="routes"):
        routes._run_refresh("大安區")
    assert any("Scrape failed" in record.message for record in caplog.records)


def test_run_refresh_skips_bad_row_but_still_persists_others(monkeypatch, caplog):
    rows = [
        {
            "case_number": "BAD-001", "court": "台北地院", "district": "大安區",
            "address": "台北市大安區仁愛路一段1號", "floor_price": 1_000_000,
            "area": 10.0, "property_type": "住宅", "auction_count": 1,
            "auction_date": "2026-05-01", "auction_url": "https://example.com/bad",
        },
        {
            "case_number": "GOOD-001", "court": "台北地院", "district": "大安區",
            "address": "台北市大安區仁愛路二段2號", "floor_price": 2_000_000,
            "area": 20.0, "property_type": "住宅", "auction_count": 1,
            "auction_date": "2026-05-02", "auction_url": "https://example.com/good",
        },
    ]
    monkeypatch.setattr(routes, "scrape_district", lambda district: rows)
    monkeypatch.setattr(routes, "fetch_avg_prices", lambda district: [])
    # Force the no-geocoding path deterministically, regardless of whatever
    # the environment running this test happens to have set — otherwise a
    # dev machine or CI with GOOGLE_MAPS_API_KEY set would make real,
    # billed, flaky network calls here.
    monkeypatch.setattr(routes, "GOOGLE_API_KEY", "")

    original_upsert = routes.upsert_property

    def _flaky_upsert(row):
        if row["case_number"] == "BAD-001":
            raise RuntimeError("DB write failed")
        original_upsert(row)

    monkeypatch.setattr(routes, "upsert_property", _flaky_upsert)

    cache_meta_calls = []
    monkeypatch.setattr(
        routes, "upsert_cache_meta", lambda district: cache_meta_calls.append(district)
    )

    with caplog.at_level(logging.ERROR, logger="routes"):
        routes._run_refresh("大安區")

    assert any("Failed to process row" in record.message for record in caplog.records)

    # Query raw (not via /api/properties, which filters out rows with no
    # lat — both rows lack coordinates here since GOOGLE_API_KEY is forced
    # empty above) to confirm the good row persisted despite the bad one.
    conn = database.get_connection()
    case_numbers = {
        row["case_number"]
        for row in conn.execute("SELECT case_number FROM properties").fetchall()
    }
    conn.close()
    assert "GOOD-001" in case_numbers
    assert "BAD-001" not in case_numbers

    # cache_meta must still advance even though one row errored out, so the
    # refresh isn't silently treated as stale/never-happened. Asserted via
    # the monkeypatched call directly (not get_cache_meta()'s current value)
    # since the autouse fixture already seeds a non-None cache_meta row for
    # this district before every test runs — checking "is not None" alone
    # wouldn't actually prove this call happened.
    assert cache_meta_calls == ["大安區"]


def test_run_refresh_skips_cache_meta_update_when_every_row_fails(monkeypatch, caplog):
    rows = [{
        "case_number": "BAD-001", "court": "台北地院", "district": "大安區",
        "address": "台北市大安區仁愛路一段1號", "floor_price": 1_000_000,
        "area": 10.0, "property_type": "住宅", "auction_count": 1,
        "auction_date": "2026-05-01", "auction_url": "",
    }]
    monkeypatch.setattr(routes, "scrape_district", lambda district: rows)
    monkeypatch.setattr(routes, "fetch_avg_prices", lambda district: [])
    monkeypatch.setattr(routes, "GOOGLE_API_KEY", "")

    def _always_fails(row):
        raise RuntimeError("DB write failed")

    monkeypatch.setattr(routes, "upsert_property", _always_fails)

    cache_meta_calls = []
    monkeypatch.setattr(
        routes, "upsert_cache_meta", lambda district: cache_meta_calls.append(district)
    )

    # If every scraped row fails to process, cache_meta must NOT be touched —
    # otherwise the district looks freshly refreshed despite nothing having
    # actually persisted, blocking retries until the TTL expires.
    with caplog.at_level(logging.ERROR, logger="routes"):
        routes._run_refresh("大安區")

    assert cache_meta_calls == []
    assert any("not updating cache_meta" in record.message for record in caplog.records)
