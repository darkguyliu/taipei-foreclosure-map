# 台北市法拍屋查詢地圖 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-stack web app to query Taipei City foreclosure properties from judicial auction data and display them on Google Maps with real estate price comparison.

**Architecture:** Python + FastAPI backend scrapes 司法院拍賣公告 and 內政部實價登錄, caches results in SQLite with geocoded coordinates. React + Vite frontend presents a split-panel UI (left sidebar: filters + property list; right: Google Maps) with InfoWindow popups and localStorage favorites.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (stdlib), requests, BeautifulSoup4, React 18, Vite, Google Maps JavaScript API, Google Maps Geocoding API

---

## Chunk 1: Project Scaffold & Database Schema

### Task 1: Backend project structure and dependencies

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/main.py`
- Create: `backend/database.py`

- [ ] **Step 1: Create backend directory and requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
requests==2.31.0
beautifulsoup4==4.12.3
python-dotenv==1.0.1
```

Save to `backend/requirements.txt`.

- [ ] **Step 2: Create the SQLite schema in database.py**

```python
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
```

- [ ] **Step 3: Create conftest.py to configure pytest path**

Create `backend/conftest.py` (empty file — pytest auto-adds `backend/` to `sys.path`):

```python
# backend/conftest.py
# This file ensures pytest adds backend/ to sys.path automatically.
```

Also create `backend/pytest.ini`:

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 4: Write tests for database initialization**

```python
# backend/tests/test_database_schema.py
import sqlite3
import pytest
import database

# Use a named shared in-memory DB (unique name avoids colliding with other test modules).
_TEST_DB = "file:testdb_schema?mode=memory&cache=shared&uri=true"
database.DB_PATH = _TEST_DB

from database import init_db, get_connection


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
        conn.commit()
    conn.close()
```

- [ ] **Step 5: Run tests**

```bash
cd backend
pip install -r requirements.txt
pip install pytest
pytest tests/test_database_schema.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 6: Create minimal FastAPI app**

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db

app = FastAPI(title="法拍屋 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Verify server starts**

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000/health` — expect `{"status": "ok"}`.

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: backend scaffold with SQLite schema and FastAPI app"
```

---

### Task 2: Frontend project structure

**Files:**
- Create: `frontend/` (Vite scaffold)
- Create: `frontend/vite.config.js`
- Create: `frontend/.env.example`

- [ ] **Step 1: Scaffold React + Vite project**

```bash
cd /Users/davidchliu/Documents/code/AI/法拍屋
npm create vite@latest frontend -- --template react
cd frontend
npm install
```

- [ ] **Step 2: Install Google Maps package**

```bash
cd frontend
npm install @vis.gl/react-google-maps
```

- [ ] **Step 3: Configure Vite proxy**

Replace `frontend/vite.config.js` with:

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 4: Create .env.example**

```
VITE_GOOGLE_MAPS_API_KEY=your_key_here
```

Save to `frontend/.env.example`. **Manual developer action (not automated):** copy this file to `frontend/.env` and replace `your_key_here` with the actual Google Maps API key before running the frontend.

- [ ] **Step 5: Add .gitignore entries**

Append to `.gitignore` (create at repo root if not present):

```
.env
frontend/.env
backend/data.db
.superpowers/
__pycache__/
*.pyc
node_modules/
frontend/dist/
```

- [ ] **Step 6: Verify frontend starts**

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173` — expect default Vite React page.

- [ ] **Step 7: Commit**

```bash
git add frontend/ .gitignore
git commit -m "feat: frontend scaffold with Vite + React + Google Maps dep"
```

---

## Chunk 2: Backend Data Pipeline

### Task 3: Property type mapper

**Files:**
- Create: `backend/property_type_mapper.py`
- Create: `backend/tests/test_property_type_mapper.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_property_type_mapper.py
from property_type_mapper import normalize_property_type


def test_住宅_keywords():
    assert normalize_property_type("公寓") == "住宅"
    assert normalize_property_type("住宅大樓") == "住宅"
    assert normalize_property_type("套房") == "住宅"
    assert normalize_property_type("透天厝") == "住宅"


def test_商辦_keywords():
    assert normalize_property_type("辦公室") == "商辦"
    assert normalize_property_type("商業大樓") == "商辦"
    assert normalize_property_type("店面") == "商辦"
    assert normalize_property_type("廠辦") == "商辦"


def test_土地_keywords():
    assert normalize_property_type("土地") == "土地"
    assert normalize_property_type("農地") == "土地"
    assert normalize_property_type("建地") == "土地"


def test_其他_fallback():
    assert normalize_property_type("停車位") == "其他"
    assert normalize_property_type("倉庫") == "其他"
    assert normalize_property_type("") == "其他"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
pytest tests/test_property_type_mapper.py -v
```

Expected: ImportError or 4 tests FAIL.

- [ ] **Step 3: Implement property_type_mapper.py**

```python
# backend/property_type_mapper.py

_RULES = [
    ("住宅", ["公寓", "住宅", "套房", "大樓", "透天", "別墅", "樓層"]),
    ("商辦", ["辦公", "商業", "店面", "廠辦", "商辦", "事務所"]),
    ("土地", ["土地", "農地", "建地", "林地", "田"]),
]


def normalize_property_type(raw: str) -> str:
    """Map raw judicial auction type string to one of: 住宅/商辦/土地/其他."""
    for normalized, keywords in _RULES:
        for kw in keywords:
            if kw in raw:
                return normalized
    return "其他"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend
pytest tests/test_property_type_mapper.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/property_type_mapper.py backend/tests/test_property_type_mapper.py
git commit -m "feat: property type normalizer with keyword mapping"
```

---

### Task 4: Address normalizer and geocoder

**Files:**
- Create: `backend/geocoder.py`
- Create: `backend/tests/test_geocoder.py`

- [ ] **Step 1: Write failing tests for address normalization**

```python
# backend/tests/test_geocoder.py
import pytest
from unittest.mock import patch, MagicMock
from geocoder import normalize_address, geocode_address


def test_normalize_removes_floor():
    assert normalize_address("台北市大安區敦化南路一段100號3樓") == "台北市大安區敦化南路一段100號"


def test_normalize_removes_room():
    assert normalize_address("台北市信義區忠孝東路五段200號之5") == "台北市信義區忠孝東路五段200號"


def test_normalize_removes_floor_and_room():
    assert normalize_address("台北市中山區南京東路二段50號5樓之3") == "台北市中山區南京東路二段50號"


def test_normalize_no_change_needed():
    assert normalize_address("台北市大安區和平東路二段300號") == "台北市大安區和平東路二段300號"


def test_geocode_returns_lat_lng():
    mock_response = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 25.04, "lng": 121.54}}}],
    }
    with patch("geocoder.requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: mock_response)
        lat, lng = geocode_address("台北市大安區敦化南路一段100號", api_key="fake")
    assert lat == pytest.approx(25.04)
    assert lng == pytest.approx(121.54)


def test_geocode_returns_none_on_zero_results():
    mock_response = {"status": "ZERO_RESULTS", "results": []}
    with patch("geocoder.requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: mock_response)
        result = geocode_address("不存在的地址", api_key="fake")
    assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
pytest tests/test_geocoder.py -v
```

Expected: ImportError or 6 tests FAIL.

- [ ] **Step 3: Implement geocoder.py**

```python
# backend/geocoder.py
import re
import logging
import requests

logger = logging.getLogger(__name__)

_FLOOR_PATTERN = re.compile(r"\d+樓(之\d+)?$")
_ROOM_PATTERN = re.compile(r"號之\d+")


def normalize_address(address: str) -> str:
    """Strip floor/unit suffixes, keep street number for geocode cache key."""
    addr = _FLOOR_PATTERN.sub("", address).strip()
    addr = _ROOM_PATTERN.sub("號", addr).strip()
    return addr


def geocode_address(address: str, api_key: str) -> tuple[float, float] | None:
    """Return (lat, lng) for address via Google Geocoding API, or None on failure."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        resp = requests.get(url, params={"address": address, "key": api_key}, timeout=10)
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
        logger.warning("Geocode failed for '%s': status=%s", address, data.get("status"))
        return None
    except Exception as exc:
        logger.warning("Geocode exception for '%s': %s", address, exc)
        return None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend
pytest tests/test_geocoder.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/geocoder.py backend/tests/test_geocoder.py
git commit -m "feat: address normalizer and Google Geocoding API wrapper"
```

---

### Task 5: Database upsert helpers

**Files:**
- Modify: `backend/database.py`
- Create: `backend/tests/test_database_ops.py`

- [ ] **Step 1: Write failing tests for upsert functions**

Create `backend/tests/test_database_ops.py`:

```python
# backend/tests/test_database_ops.py
import pytest
import database

# Distinct named DB from test_database_schema.py to avoid cross-module state sharing.
_TEST_DB = "file:testdb_ops?mode=memory&cache=shared&uri=true"
database.DB_PATH = _TEST_DB

from database import init_db, upsert_property, upsert_avg_price, upsert_cache_meta, get_properties, get_avg_prices


@pytest.fixture(autouse=True)
def fresh_db():
    """Re-initialize schema before each test to isolate state."""
    init_db()
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
    住宅_price = next(p for p in prices if p["property_type"] == "住宅")
    assert 住宅_price["avg_price"] == 90.0


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
```

- [ ] **Step 2: Run tests to confirm new tests fail**

```bash
cd backend
pytest tests/test_database_ops.py -v
```

Expected: 4 tests FAIL with ImportError or AttributeError.

- [ ] **Step 3: Implement upsert functions in database.py**

Append to `backend/database.py`:

```python
def upsert_property(prop: dict) -> None:
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
                 datetime('now', 'localtime'))
            ON CONFLICT(case_number) DO UPDATE SET
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


def get_properties(
    district: str,
    min_price: int | None = None,
    max_price: int | None = None,
    auction_count: int | None = None,
    property_type: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM properties WHERE district = ? AND lat IS NOT NULL"
    params: list = [district]
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


def get_avg_prices(district: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM avg_prices WHERE district = ?", (district,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_cache_meta(district: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cache_meta WHERE district = ?", (district,)
        ).fetchone()
    return dict(row) if row else None


def get_property_by_id(property_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM properties WHERE id = ?", (property_id,)
        ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: Run all database tests**

```bash
cd backend
pytest tests/test_database_schema.py tests/test_database_ops.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py backend/tests/test_database_schema.py backend/tests/test_database_ops.py
git commit -m "feat: database upsert helpers and filtered property queries"
```

---

### Task 6: Real estate price fetcher (實價登錄)

**Files:**
- Create: `backend/realtime_prices.py`
- Create: `backend/tests/test_realtime_prices.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_realtime_prices.py
from unittest.mock import patch, MagicMock
from realtime_prices import fetch_avg_prices


MOCK_API_RESPONSE = [
    {"鄉鎮市區": "大安區", "建物型態": "住宅大樓", "單價元平方公尺": "265000"},
    {"鄉鎮市區": "大安區", "建物型態": "住宅大樓", "單價元平方公尺": "280000"},
    {"鄉鎮市區": "大安區", "建物型態": "辦公商業大樓", "單價元平方公尺": "310000"},
]


def test_fetch_avg_prices_returns_list():
    with patch("realtime_prices.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: MOCK_API_RESPONSE,
            raise_for_status=lambda: None,
        )
        results = fetch_avg_prices("大安區")
    assert isinstance(results, list)
    assert len(results) >= 1


def test_fetch_avg_prices_calculates_correctly():
    with patch("realtime_prices.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: MOCK_API_RESPONSE,
            raise_for_status=lambda: None,
        )
        results = fetch_avg_prices("大安區")
    住宅_entry = next((r for r in results if r["property_type"] == "住宅"), None)
    assert 住宅_entry is not None
    # avg of 265000 and 280000 sqm → convert to 坪 (1坪 = 3.30579 sqm)
    # avg_sqm = 272500, per_ping = 272500 * 3.30579 / 10000 ≈ 90.1 萬/坪
    assert 85 < 住宅_entry["avg_price"] < 95
    assert 住宅_entry["sample_count"] == 2
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
pytest tests/test_realtime_prices.py -v
```

Expected: ImportError or 2 tests FAIL.

- [ ] **Step 3: Implement realtime_prices.py**

```python
# backend/realtime_prices.py
"""
Fetches district average prices from 內政部不動產交易實價登錄 Open Data API.
API docs: https://plvr.land.moi.gov.tw/DownloadOpenData
No API key required.
"""
import logging
import requests
from property_type_mapper import normalize_property_type
from collections import defaultdict

logger = logging.getLogger(__name__)

# 內政部實價登錄 Open Data endpoint (CSV/JSON for recent transactions)
_API_URL = (
    "https://plvr.land.moi.gov.tw/DownloadSeason"
    "?type=json&fileName=a_lvr_land_a.json"
)

_SQM_TO_PING = 3.30579  # 1 坪 = 3.30579 平方公尺


def fetch_avg_prices(district: str) -> list[dict]:
    """
    Return list of {property_type, avg_price (萬/坪), sample_count} for district.
    Falls back to empty list on any error.
    """
    try:
        resp = requests.get(_API_URL, timeout=30)
        resp.raise_for_status()
        records = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch avg prices: %s", exc)
        return []

    buckets: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        if rec.get("鄉鎮市區") != district:
            continue
        raw_type = rec.get("建物型態", "")
        unit_price_sqm = rec.get("單價元平方公尺", "")
        if not unit_price_sqm:
            continue
        try:
            price_sqm = float(unit_price_sqm)
        except ValueError:
            continue
        normalized = normalize_property_type(raw_type)
        price_ping = price_sqm * _SQM_TO_PING / 10_000  # convert to 萬/坪
        buckets[normalized].append(price_ping)

    results = []
    for property_type, prices in buckets.items():
        results.append({
            "property_type": property_type,
            "avg_price": round(sum(prices) / len(prices), 1),
            "sample_count": len(prices),
        })
    return results
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend
pytest tests/test_realtime_prices.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/realtime_prices.py backend/tests/test_realtime_prices.py
git commit -m "feat: 實價登錄 avg price fetcher with 坪 conversion"
```

---

### Task 7: 司法院 scraper

**Files:**
- Create: `backend/scraper.py`
- Create: `backend/tests/test_scraper.py`

- [ ] **Step 1: Write failing tests using fixture HTML**

```python
# backend/tests/test_scraper.py
import pytest
from scraper import parse_auction_rows

SAMPLE_HTML = """
<table class="tableAuction">
  <tr>
    <td>113司執字第12345號</td>
    <td>臺灣臺北地方法院</td>
    <td>台北市大安區敦化南路一段100號3樓</td>
    <td>住宅大樓</td>
    <td>35.70坪</td>
    <td>12,000,000</td>
    <td>1</td>
    <td>114/02/21</td>
    <td><a href="/case/123">公告</a></td>
  </tr>
  <tr>
    <td>113司執字第99999號</td>
    <td>臺灣臺北地方法院</td>
    <td>台北市大安區和平東路二段200號</td>
    <td>公寓</td>
    <td>25.00坪</td>
    <td>5,500,000</td>
    <td>2</td>
    <td>114/03/05</td>
    <td><a href="/case/456">公告</a></td>
  </tr>
</table>
"""


def test_parse_returns_correct_count():
    rows = parse_auction_rows(SAMPLE_HTML, district="大安區")
    assert len(rows) == 2


def test_parse_extracts_fields():
    rows = parse_auction_rows(SAMPLE_HTML, district="大安區")
    row = rows[0]
    assert row["case_number"] == "113司執字第12345號"
    assert row["court"] == "臺灣臺北地方法院"
    assert row["address"] == "台北市大安區敦化南路一段100號3樓"
    assert row["floor_price"] == 12_000_000
    assert row["area"] == pytest.approx(35.70)
    assert row["auction_count"] == 1
    assert row["auction_date"] == "2025-02-21"  # ROC 114 + 1911 = 2025


def test_parse_skips_wrong_district():
    rows = parse_auction_rows(SAMPLE_HTML, district="信義區")
    assert len(rows) == 0


def test_parse_normalizes_property_type():
    rows = parse_auction_rows(SAMPLE_HTML, district="大安區")
    # "住宅大樓" → "住宅", "公寓" → "住宅"
    assert all(r["property_type"] == "住宅" for r in rows)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
pytest tests/test_scraper.py -v
```

Expected: ImportError or FAIL.

- [ ] **Step 3: Implement scraper.py**

```python
# backend/scraper.py
"""
Scrapes 司法院拍賣公告 (aomp109.judicial.gov.tw).
The site uses a POST form for search. Results are paginated.
"""
import logging
import re
import requests
from bs4 import BeautifulSoup
from property_type_mapper import normalize_property_type

logger = logging.getLogger(__name__)

BASE_URL = "https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02.htm"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


def _roc_to_ad_date(roc_date: str) -> str:
    """Convert ROC date '114/02/21' to AD '2026-02-21'."""
    parts = roc_date.strip().split("/")
    if len(parts) != 3:
        return roc_date
    year = int(parts[0]) + 1911
    return f"{year}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"


def _parse_price(text: str) -> int:
    """Parse '12,000,000' → 12000000."""
    return int(re.sub(r"[^\d]", "", text))


def _parse_area(text: str) -> float:
    """Parse '35.70坪' → 35.70."""
    match = re.search(r"[\d.]+", text)
    return float(match.group()) if match else 0.0


def parse_auction_rows(html: str, district: str) -> list[dict]:
    """Parse table rows from auction result HTML. Only returns rows matching district."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="tableAuction")
    if not table:
        return []

    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue
        address = tds[2].get_text(strip=True)
        if district not in address:
            continue
        link_tag = tds[8].find("a")
        auction_url = f"https://aomp109.judicial.gov.tw{link_tag['href']}" if link_tag else ""
        rows.append({
            "case_number": tds[0].get_text(strip=True),
            "court": tds[1].get_text(strip=True),
            "address": address,
            "property_type": normalize_property_type(tds[3].get_text(strip=True)),
            "area": _parse_area(tds[4].get_text(strip=True)),
            "floor_price": _parse_price(tds[5].get_text(strip=True)),
            "auction_count": int(re.sub(r"[^\d]", "", tds[6].get_text(strip=True)) or 1),
            "auction_date": _roc_to_ad_date(tds[7].get_text(strip=True)),
            "auction_url": auction_url,
            "district": district,
        })
    return rows


def scrape_district(district: str) -> list[dict]:
    """
    Fetch all auction listings for a Taipei district.
    Raises requests.RequestException on connection failure (caller handles).
    """
    payload = {
        "cityCode": "63",   # 台北市
        "townCode": "",
        "keyword": district,
        "page": "1",
    }
    all_rows = []
    page = 1
    while True:
        payload["page"] = str(page)
        resp = requests.post(BASE_URL, data=payload, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        rows = parse_auction_rows(resp.text, district)
        all_rows.extend(rows)
        # Stop if last page (no new rows or explicit end marker)
        if not rows:
            break
        page += 1
        if page > 20:  # safety cap
            break
    logger.info("Scraped %d rows for %s", len(all_rows), district)
    return all_rows
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend
pytest tests/test_scraper.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scraper.py backend/tests/test_scraper.py
git commit -m "feat: 司法院 auction scraper with ROC date conversion"
```

---

## Chunk 3: Backend API Endpoints

### Task 8: FastAPI routes

**Files:**
- Create: `backend/routes.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing API tests**

```python
# backend/tests/test_routes.py
import pytest
from fastapi.testclient import TestClient
import database

database.DB_PATH = "file:testdb_routes?mode=memory&cache=shared&uri=true"
from database import init_db
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    from database import upsert_property, upsert_avg_price, upsert_cache_meta
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
pytest tests/test_routes.py -v
```

Expected: 5 tests FAIL (routes not defined).

- [ ] **Step 3: Create routes.py**

```python
# backend/routes.py
import logging
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import (
    get_properties, get_avg_prices, get_cache_meta,
    get_property_by_id, upsert_property, upsert_avg_price,
    upsert_cache_meta,
)
from scraper import scrape_district
from geocoder import normalize_address, geocode_address
from realtime_prices import fetch_avg_prices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


@router.get("/properties")
def list_properties(
    district: str,
    min_price: int | None = None,
    max_price: int | None = None,
    auction_count: int | None = None,
    property_type: str | None = None,
):
    props = get_properties(district, min_price, max_price, auction_count, property_type)
    meta = get_cache_meta(district)
    return {
        "district": district,
        "total": len(props),
        "last_refreshed_at": meta["last_refreshed_at"] if meta else None,
        "properties": props,
    }


@router.get("/properties/{property_id}")
def get_property(property_id: int):
    prop = get_property_by_id(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.get("/avg-prices")
def avg_prices(district: str):
    prices = get_avg_prices(district)
    return {"district": district, "avg_prices": prices}


@router.post("/refresh")
def refresh(district: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_refresh, district)
    return {"status": "started", "district": district}


def _run_refresh(district: str) -> None:
    logger.info("Starting refresh for %s", district)
    # 1. Scrape
    rows = scrape_district(district)

    # 2. Geocode + normalize + persist
    geocoded_new = geocoded_cached = failed = 0
    for row in rows:
        # property_type already normalized by scraper's parse_auction_rows
        addr_norm = normalize_address(row["address"])
        row["address_norm"] = addr_norm

        # Check geocode cache via existing properties
        from database import get_db
        with get_db() as conn:
            cached = conn.execute(
                "SELECT lat, lng FROM properties WHERE address_norm = ? AND lat IS NOT NULL LIMIT 1",
                (addr_norm,),
            ).fetchone()

        if cached:
            row["lat"], row["lng"] = cached["lat"], cached["lng"]
            geocoded_cached += 1
        elif GOOGLE_API_KEY:
            result = geocode_address(addr_norm, GOOGLE_API_KEY)
            if result:
                row["lat"], row["lng"] = result
                geocoded_new += 1
            else:
                row["lat"] = row["lng"] = None
                failed += 1
        else:
            row["lat"] = row["lng"] = None
            failed += 1

        upsert_property(row)

    # 3. Fetch avg prices
    avg_price_list = fetch_avg_prices(district)
    for entry in avg_price_list:
        upsert_avg_price(district, entry["property_type"], entry["avg_price"], entry["sample_count"])

    # 4. Update cache meta
    upsert_cache_meta(district)
    logger.info(
        "Refresh done for %s: scraped=%d new_geocode=%d cached=%d failed=%d",
        district, len(rows), geocoded_new, geocoded_cached, failed,
    )
```

- [ ] **Step 4: Register routes in main.py**

Replace `backend/main.py` with:

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes import router

app = FastAPI(title="法拍屋 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run all tests**

```bash
cd backend
pytest tests/test_routes.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
cd backend
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/routes.py backend/main.py backend/tests/test_routes.py
git commit -m "feat: FastAPI routes for properties, avg-prices, and refresh"
```

---

## Chunk 4: Frontend Core

### Task 9: API hooks

**Files:**
- Create: `frontend/src/hooks/useProperties.js`
- Create: `frontend/src/hooks/useAvgPrices.js`
- Create: `frontend/src/hooks/useFavorites.js`

- [ ] **Step 1: Create useProperties hook**

```js
// frontend/src/hooks/useProperties.js
import { useState, useEffect } from 'react'

export function useProperties(district, filters = {}) {
  const [properties, setProperties] = useState([])
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!district) return
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ district })
    if (filters.minPrice) params.set('min_price', filters.minPrice)
    if (filters.maxPrice) params.set('max_price', filters.maxPrice)
    if (filters.auctionCount) params.set('auction_count', filters.auctionCount)
    if (filters.propertyType && filters.propertyType !== 'all')
      params.set('property_type', filters.propertyType)

    fetch(`/api/properties?${params}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        setProperties(data.properties)
        setLastRefreshedAt(data.last_refreshed_at)
      })
      .catch(err => setError(`無法載入資料: ${err}`))
      .finally(() => setLoading(false))
  }, [district, filters.minPrice, filters.maxPrice, filters.auctionCount, filters.propertyType])

  return { properties, lastRefreshedAt, loading, error }
}
```

- [ ] **Step 2: Create useAvgPrices hook**

```js
// frontend/src/hooks/useAvgPrices.js
import { useState, useEffect } from 'react'

export function useAvgPrices(district) {
  const [avgPrices, setAvgPrices] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!district) return
    setLoading(true)
    fetch(`/api/avg-prices?district=${encodeURIComponent(district)}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => setAvgPrices(data.avg_prices))
      .catch(() => setAvgPrices([]))
      .finally(() => setLoading(false))
  }, [district])

  // Returns avg price in 萬/坪 for a given property_type
  function getAvgPrice(propertyType) {
    const entry = avgPrices.find(p => p.property_type === propertyType)
    return entry ? entry.avg_price : null
  }

  return { avgPrices, loading, getAvgPrice }
}
```

- [ ] **Step 3: Create useFavorites hook**

```js
// frontend/src/hooks/useFavorites.js
import { useState, useEffect } from 'react'

const STORAGE_KEY = 'foreclosure_favorites'

export function useFavorites() {
  const [favoriteIds, setFavoriteIds] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    } catch {
      return []
    }
  })

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(favoriteIds))
  }, [favoriteIds])

  function toggleFavorite(id) {
    setFavoriteIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  function isFavorite(id) {
    return favoriteIds.includes(id)
  }

  return { favoriteIds, toggleFavorite, isFavorite }
}
```

- [ ] **Step 4: Verify no syntax errors**

```bash
cd frontend
npm run build 2>&1 | head -20
```

Expected: build completes (or only reports missing env var for Maps key, not syntax errors).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: useProperties, useAvgPrices, useFavorites hooks"
```

---

### Task 10: App shell and district selector

**Files:**
- Modify: `frontend/src/App.jsx`
- Create: `frontend/src/components/DistrictSelector.jsx`
- Modify: `frontend/index.html`

- [ ] **Step 1: Define Taipei districts constant**

Create `frontend/src/constants.js`:

```js
export const TAIPEI_DISTRICTS = [
  '中正區', '大同區', '中山區', '松山區', '大安區',
  '萬華區', '信義區', '士林區', '北投區', '內湖區',
  '南港區', '文山區',
]
```

- [ ] **Step 2: Create DistrictSelector component**

```jsx
// frontend/src/components/DistrictSelector.jsx
import { TAIPEI_DISTRICTS } from '../constants'

export function DistrictSelector({ selected, onChange }) {
  return (
    <div className="district-selector">
      <label htmlFor="district-select">選擇區域</label>
      <select
        id="district-select"
        value={selected}
        onChange={e => onChange(e.target.value)}
      >
        <option value="">-- 請選擇 --</option>
        {TAIPEI_DISTRICTS.map(d => (
          <option key={d} value={d}>{d}</option>
        ))}
      </select>
    </div>
  )
}
```

- [ ] **Step 3: Replace App.jsx with layout shell**

```jsx
// frontend/src/App.jsx
import { useState, useEffect } from 'react'
import { APIProvider } from '@vis.gl/react-google-maps'
import { DistrictSelector } from './components/DistrictSelector'
import { Sidebar } from './components/Sidebar'
import { MapView } from './components/MapView'
import { useProperties } from './hooks/useProperties'
import { useAvgPrices } from './hooks/useAvgPrices'
import { useFavorites } from './hooks/useFavorites'
import './App.css'

const MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''

export default function App() {
  const [district, setDistrict] = useState('')
  const [filters, setFilters] = useState({})
  const [selectedProperty, setSelectedProperty] = useState(null)
  const [activeTab, setActiveTab] = useState('all') // 'all' | 'favorites'

  const { properties, lastRefreshedAt, loading, error } = useProperties(district, filters)
  const { getAvgPrice } = useAvgPrices(district)
  const { favoriteIds, toggleFavorite, isFavorite } = useFavorites()

  async function handleRefresh() {
    if (!district) return
    await fetch(`/api/refresh?district=${encodeURIComponent(district)}`, { method: 'POST' })
    // Reload after a short delay to allow background task to complete
    setTimeout(() => window.location.reload(), 3000)
  }

  const displayProperties = activeTab === 'favorites'
    ? properties.filter(p => favoriteIds.includes(p.id))
    : properties

  // Fetch any favorited properties not in the current district's loaded data
  const [crossDistrictFavs, setCrossDistrictFavs] = useState([])
  useEffect(() => {
    if (activeTab !== 'favorites') return
    const missingIds = favoriteIds.filter(id => !properties.some(p => p.id === id))
    Promise.all(missingIds.map(id =>
      fetch(`/api/properties/${id}`).then(r => r.ok ? r.json() : null)
    )).then(results => setCrossDistrictFavs(results.filter(Boolean)))
  }, [activeTab, favoriteIds, properties])

  const favoritesDisplay = activeTab === 'favorites'
    ? [...displayProperties, ...crossDistrictFavs.filter(p => !displayProperties.some(d => d.id === p.id))]
    : displayProperties

  return (
    <APIProvider apiKey={MAPS_API_KEY}>
      <div className="app-layout">
        <header className="app-header">
          <span className="app-title">🏠 台北法拍屋地圖</span>
          <DistrictSelector selected={district} onChange={setDistrict} />
          {district && (
            <button className="refresh-btn" onClick={handleRefresh}>
              🔄 刷新資料
            </button>
          )}
        </header>
        <div className="app-body">
          <Sidebar
            properties={activeTab === 'favorites' ? favoritesDisplay : displayProperties}
            totalCount={properties.length}
            loading={loading}
            error={error}
            lastRefreshedAt={lastRefreshedAt}
            filters={filters}
            onFiltersChange={setFilters}
            selectedProperty={selectedProperty}
            onSelectProperty={setSelectedProperty}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            isFavorite={isFavorite}
            toggleFavorite={toggleFavorite}
            getAvgPrice={getAvgPrice}
          />
          <MapView
            properties={properties}
            selectedProperty={selectedProperty}
            onSelectProperty={setSelectedProperty}
            isFavorite={isFavorite}
            toggleFavorite={toggleFavorite}
            getAvgPrice={getAvgPrice}
          />
        </div>
      </div>
    </APIProvider>
  )
}
```

- [ ] **Step 4: Add base CSS**

Create `frontend/src/App.css`:

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0f0f1a;
  color: #e0e0e0;
  height: 100vh;
  overflow: hidden;
}

.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
  background: #1a1a2e;
  border-bottom: 1px solid #2a2a4a;
  flex-shrink: 0;
}

.app-title {
  font-size: 18px;
  font-weight: bold;
  color: #7c7cff;
  white-space: nowrap;
}

.app-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.district-selector label {
  margin-right: 8px;
  font-size: 14px;
  color: #aaa;
}

.district-selector select {
  background: #2a2a4a;
  color: #e0e0e0;
  border: 1px solid #3a3a6a;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 14px;
  cursor: pointer;
}

.refresh-btn {
  background: #1a3a1a;
  color: #7cff7c;
  border: 1px solid #3a6a3a;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 14px;
  cursor: pointer;
}

.refresh-btn:hover { background: #2a4a2a; }
```

- [ ] **Step 5: Verify app renders without errors**

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173` — expect header with district selector to render.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat: App shell with district selector and layout structure"
```

---

## Chunk 5: Frontend Components

### Task 11: FilterPanel component

**Files:**
- Create: `frontend/src/components/FilterPanel.jsx`

- [ ] **Step 1: Create FilterPanel**

```jsx
// frontend/src/components/FilterPanel.jsx
export function FilterPanel({ filters, onChange }) {
  function update(key, value) {
    onChange({ ...filters, [key]: value || undefined })
  }

  return (
    <div className="filter-panel">
      <div className="filter-row">
        <label>底價下限（萬）</label>
        <input
          type="number"
          min="0"
          placeholder="不限"
          value={filters.minPrice ? filters.minPrice / 10000 : ''}
          onChange={e => update('minPrice', e.target.value ? Number(e.target.value) * 10000 : null)}
        />
      </div>
      <div className="filter-row">
        <label>底價上限（萬）</label>
        <input
          type="number"
          min="0"
          placeholder="不限"
          value={filters.maxPrice ? filters.maxPrice / 10000 : ''}
          onChange={e => update('maxPrice', e.target.value ? Number(e.target.value) * 10000 : null)}
        />
      </div>
      <div className="filter-row">
        <label>拍次</label>
        <select value={filters.auctionCount || 'all'} onChange={e => update('auctionCount', e.target.value === 'all' ? null : Number(e.target.value))}>
          <option value="all">全部</option>
          <option value="1">第1拍</option>
          <option value="2">第2拍</option>
          <option value="3">第3拍以上</option>
        </select>
      </div>
      <div className="filter-row">
        <label>類型</label>
        <select value={filters.propertyType || 'all'} onChange={e => update('propertyType', e.target.value === 'all' ? null : e.target.value)}>
          <option value="all">全部</option>
          <option value="住宅">住宅</option>
          <option value="商辦">商辦</option>
          <option value="土地">土地</option>
          <option value="其他">其他</option>
        </select>
      </div>
    </div>
  )
}
```

Add to `App.css`:

```css
.filter-panel { display: flex; flex-direction: column; gap: 8px; }

.filter-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-row label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }

.filter-row input, .filter-row select {
  background: #111;
  color: #e0e0e0;
  border: 1px solid #333;
  border-radius: 5px;
  padding: 6px 8px;
  font-size: 13px;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/FilterPanel.jsx frontend/src/App.css
git commit -m "feat: FilterPanel component for price/count/type filters"
```

---

### Task 12: PropertyCard component

**Files:**
- Create: `frontend/src/components/PropertyCard.jsx`

- [ ] **Step 1: Create PropertyCard**

```jsx
// frontend/src/components/PropertyCard.jsx

const AUCTION_COLORS = { 1: '#4a8fd4', 2: '#f4a430', 3: '#ff6b6b' }

export function PropertyCard({ property, isSelected, isFavorite, onSelect, onToggleFavorite }) {
  const color = AUCTION_COLORS[property.auction_count] || '#ff6b6b'
  return (
    <div
      className={`property-card ${isSelected ? 'selected' : ''}`}
      style={{ borderLeft: `3px solid ${color}` }}
      onClick={() => onSelect(property)}
    >
      <div className="property-card-address">{property.address}</div>
      <div className="property-card-meta">
        <span>底價 {(property.floor_price / 10000).toFixed(0)}萬</span>
        <span>第{property.auction_count}拍</span>
        <span>{property.auction_date}</span>
      </div>
      <div className="property-card-actions">
        <button
          className={`fav-btn ${isFavorite ? 'active' : ''}`}
          onClick={e => { e.stopPropagation(); onToggleFavorite(property.id) }}
        >
          {isFavorite ? '⭐' : '☆'} 收藏
        </button>
      </div>
    </div>
  )
}
```

Add to `App.css`:

```css
.property-card {
  background: #1e1e2e;
  border-radius: 6px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.property-card:hover, .property-card.selected { background: #2a2a4a; }

.property-card-address { font-size: 13px; color: #e0e0e0; margin-bottom: 4px; }

.property-card-meta {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: #888;
  margin-bottom: 6px;
}

.property-card-actions { display: flex; gap: 6px; }

.fav-btn {
  font-size: 11px;
  background: #111;
  border: 1px solid #333;
  border-radius: 4px;
  color: #aaa;
  padding: 3px 8px;
  cursor: pointer;
}

.fav-btn.active { color: #f4c430; border-color: #f4c430; }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/PropertyCard.jsx frontend/src/App.css
git commit -m "feat: PropertyCard with auction count color and favorite toggle"
```

---

### Task 13: Sidebar component

**Files:**
- Create: `frontend/src/components/Sidebar.jsx`

- [ ] **Step 1: Create Sidebar**

```jsx
// frontend/src/components/Sidebar.jsx
import { FilterPanel } from './FilterPanel'
import { PropertyCard } from './PropertyCard'

export function Sidebar({
  properties, totalCount, loading, error, lastRefreshedAt,
  filters, onFiltersChange,
  selectedProperty, onSelectProperty,
  activeTab, onTabChange,
  isFavorite, toggleFavorite,
  getAvgPrice,
}) {
  // Show住宅 avg price as summary
  const residentialAvg = getAvgPrice('住宅')

  return (
    <aside className="sidebar">
      <FilterPanel filters={filters} onChange={onFiltersChange} />

      {residentialAvg && (
        <div className="avg-price-banner">
          💰 住宅均價 <strong>{residentialAvg} 萬/坪</strong>
          {lastRefreshedAt && (
            <span className="refreshed-at">
              更新於 {new Date(lastRefreshedAt).toLocaleString('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      )}

      <div className="tab-bar">
        <button className={activeTab === 'all' ? 'active' : ''} onClick={() => onTabChange('all')}>
          全部 ({totalCount})
        </button>
        <button className={activeTab === 'favorites' ? 'active' : ''} onClick={() => onTabChange('favorites')}>
          收藏
        </button>
      </div>

      <div className="property-list">
        {loading && <p className="list-msg">載入中...</p>}
        {error && <p className="list-msg error">{error}</p>}
        {!loading && !error && properties.length === 0 && (
          <p className="list-msg">
            {activeTab === 'favorites' ? '尚無收藏物件' : '尚無資料，請點擊「刷新資料」'}
          </p>
        )}
        {properties.map(p => (
          <PropertyCard
            key={p.id}
            property={p}
            isSelected={selectedProperty?.id === p.id}
            isFavorite={isFavorite(p.id)}
            onSelect={onSelectProperty}
            onToggleFavorite={toggleFavorite}
          />
        ))}
      </div>
    </aside>
  )
}
```

Add to `App.css`:

```css
.sidebar {
  width: 380px;
  flex-shrink: 0;
  background: #13131f;
  border-right: 1px solid #2a2a3a;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  overflow-y: auto;
}

.avg-price-banner {
  background: #1a2e1a;
  border: 1px solid #2a4a2a;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 13px;
  color: #7cff7c;
}

.refreshed-at { display: block; font-size: 11px; color: #5a8a5a; margin-top: 2px; }

.tab-bar { display: flex; gap: 4px; }

.tab-bar button {
  flex: 1;
  background: #1e1e2e;
  color: #888;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
  padding: 6px;
  cursor: pointer;
  font-size: 13px;
}

.tab-bar button.active { background: #2a2a4a; color: #e0e0e0; border-color: #4a4a7a; }

.property-list { display: flex; flex-direction: column; gap: 6px; overflow-y: auto; }

.list-msg { font-size: 13px; color: #666; text-align: center; padding: 20px 0; }
.list-msg.error { color: #ff6b6b; }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Sidebar.jsx frontend/src/App.css
git commit -m "feat: Sidebar with filter panel, avg price, tab bar, and property list"
```

---

### Task 14: MapView component with InfoWindow

**Files:**
- Create: `frontend/src/components/MapView.jsx`

- [ ] **Step 1: Create MapView**

```jsx
// frontend/src/components/MapView.jsx
import { Map, AdvancedMarker, InfoWindow, useMap } from '@vis.gl/react-google-maps'
import { useState, useEffect } from 'react'

const TAIPEI_CENTER = { lat: 25.0478, lng: 121.5319 }
const AUCTION_COLORS = { 1: '#4a8fd4', 2: '#f4a430', 3: '#ff6b6b' }

function MarkerPin({ color }) {
  return (
    <div style={{
      width: 16, height: 16,
      background: color,
      borderRadius: '50% 50% 50% 0',
      transform: 'rotate(-45deg)',
      border: '2px solid white',
      boxShadow: `0 0 6px ${color}`,
    }} />
  )
}

export function MapView({ properties, selectedProperty, onSelectProperty, isFavorite, toggleFavorite, getAvgPrice }) {
  const map = useMap()

  // Pan to selected property
  useEffect(() => {
    if (selectedProperty && map) {
      map.panTo({ lat: selectedProperty.lat, lng: selectedProperty.lng })
    }
  }, [selectedProperty, map])

  return (
    <div className="map-container">
      <Map
        defaultCenter={TAIPEI_CENTER}
        defaultZoom={13}
        mapId="foreclosure-map"
        gestureHandling="greedy"
        disableDefaultUI={false}
      >
        {properties.map(p => (
          <AdvancedMarker
            key={p.id}
            position={{ lat: p.lat, lng: p.lng }}
            onClick={() => onSelectProperty(p)}
          >
            <MarkerPin color={AUCTION_COLORS[p.auction_count] || '#ff6b6b'} />
          </AdvancedMarker>
        ))}

        {selectedProperty && (
          <InfoWindow
            position={{ lat: selectedProperty.lat, lng: selectedProperty.lng }}
            onCloseClick={() => onSelectProperty(null)}
          >
            <PropertyInfoWindow
              property={selectedProperty}
              isFavorite={isFavorite(selectedProperty.id)}
              onToggleFavorite={() => toggleFavorite(selectedProperty.id)}
              getAvgPrice={getAvgPrice}
            />
          </InfoWindow>
        )}
      </Map>
    </div>
  )
}

function PropertyInfoWindow({ property, isFavorite, onToggleFavorite, getAvgPrice }) {
  const pricePerPing = property.area > 0
    ? ((property.floor_price / 10000) / property.area).toFixed(1)
    : null
  const avgPrice = getAvgPrice(property.property_type)
  const discount = avgPrice && pricePerPing
    ? Math.round((1 - Number(pricePerPing) / avgPrice) * 100)
    : null

  return (
    <div className="info-window">
      <div className="iw-address">{property.address}</div>
      <table className="iw-table">
        <tbody>
          <tr><td>底價</td><td><strong>{(property.floor_price / 10000).toFixed(0)} 萬</strong></td></tr>
          <tr><td>面積</td><td>{property.area} 坪</td></tr>
          <tr><td>類型</td><td>{property.property_type}</td></tr>
          <tr><td>拍次</td><td>第 {property.auction_count} 拍</td></tr>
          <tr><td>拍賣日</td><td>{property.auction_date}</td></tr>
          <tr><td>法院</td><td>{property.court}</td></tr>
          {pricePerPing && <tr><td>底價/坪</td><td>{pricePerPing} 萬</td></tr>}
          {avgPrice && <tr><td>區域均價</td><td>{avgPrice} 萬/坪</td></tr>}
          <tr><td>折扣</td><td style={{ color: discount !== null ? (discount > 0 ? '#7cff7c' : '#ff6b6b') : '#999' }}>
            {discount === null
              ? '載入中...'
              : discount > 0 ? `低於均價 ${discount}%` : `高於均價 ${-discount}%`}
          </td></tr>
        </tbody>
      </table>
      <div className="iw-actions">
        <button onClick={onToggleFavorite} className={isFavorite ? 'active' : ''}>
          {isFavorite ? '⭐ 已收藏' : '☆ 收藏'}
        </button>
        {property.auction_url && (
          <a href={property.auction_url} target="_blank" rel="noreferrer">
            🔗 司法院公告
          </a>
        )}
      </div>
    </div>
  )
}
```

Add to `App.css`:

```css
.map-container { flex: 1; position: relative; }
.map-container > div { height: 100% !important; }

/* InfoWindow styles (rendered inside Google Maps iframe-like div) */
.info-window { min-width: 220px; font-family: inherit; color: #1a1a1a; }
.iw-address { font-weight: bold; font-size: 13px; margin-bottom: 8px; }
.iw-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.iw-table td { padding: 2px 6px; }
.iw-table td:first-child { color: #666; white-space: nowrap; }
.iw-actions { display: flex; gap: 8px; margin-top: 10px; }
.iw-actions button, .iw-actions a {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid #ccc;
  cursor: pointer;
  text-decoration: none;
  background: #f5f5f5;
  color: #333;
}
.iw-actions button.active { background: #fff8e1; border-color: #f4c430; }
```

- [ ] **Step 2: Verify app renders with map**

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`, select a district — expect map to render (if API key is set). If key missing, map shows error overlay which is expected.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MapView.jsx frontend/src/App.css
git commit -m "feat: MapView with colored markers and InfoWindow detail popup"
```

---

### Task 15: End-to-end smoke test

**Files:** none (manual verification)

- [ ] **Step 1: Start backend**

```bash
cd backend
GOOGLE_MAPS_API_KEY=your_key uvicorn main:app --reload --port 8000
```

- [ ] **Step 2: Start frontend**

```bash
cd frontend
npm run dev
```

- [ ] **Step 3: Manual verification checklist**

- [ ] Select 大安區 from dropdown
- [ ] Click 刷新資料 (wait ~5 seconds, then reload)
- [ ] Verify properties appear in sidebar list
- [ ] Verify markers appear on map with correct colors (blue/orange/red)
- [ ] Click a marker → InfoWindow appears with property details
- [ ] Verify 折扣 calculation shows if avg price is loaded
- [ ] Click ⭐ 收藏 in InfoWindow → card in sidebar shows filled star
- [ ] Switch to 收藏 tab → favorited property shows
- [ ] Test price filter: set 底價下限 = 2000萬 → list and map update
- [ ] Click 🔗 司法院公告 → opens external link in new tab

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "feat: complete taipei foreclosure map - initial working version"
```
