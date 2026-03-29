# 台北市法拍屋查詢地圖 — 設計規格

**日期**: 2026-03-29
**狀態**: 已核准

---

## 概述

一個網頁應用程式，讓使用者查詢台北市各區的法拍屋公告，並在 Google Maps 上標示位置。資料來源結合司法院拍賣公告（爬蟲）與內政部實價登錄（Open Data API），以 SQLite 快取加速查詢。

---

## 架構

### 技術棧

| 層級 | 技術 |
|------|------|
| 前端 | React + Vite |
| 後端 | Python + FastAPI |
| 資料庫 | SQLite |
| 地圖 | Google Maps JavaScript API |
| 地理編碼 | Google Maps Geocoding API |
| 資料來源 1 | 司法院拍賣公告網站（爬蟲） |
| 資料來源 2 | 內政部不動產交易實價登錄 Open Data API |

### 系統架構

```
前端 (React + Vite)
  │
  ├── GET /api/properties?district=大安區&...  →  FastAPI
  │                                                  └── 查詢 SQLite
  ├── GET /api/avg-prices?district=大安區     →  FastAPI
  │                                                  └── 查詢 SQLite (實價登錄快取)
  └── POST /api/refresh?district=大安區       →  FastAPI (本地內部端點)
                                                     ├── 爬司法院公告
                                                     ├── 呼叫 Google Geocoding API
                                                     ├── 呼叫實價登錄 API
                                                     └── 寫入 SQLite
```

### 資料流

**查詢流程（正常使用）**
1. 使用者選擇區域
2. 前端同時呼叫 `/api/properties?district=XX` 和 `/api/avg-prices?district=XX`
3. avg-prices 資料在前端 state 存放，供 InfoWindow 折扣計算使用
4. FastAPI 從 SQLite 讀取快取資料（含座標），回傳物件列表
5. 前端渲染地圖標記 + 左側物件列表
6. 使用者點擊標記 → InfoWindow 從已載入的 avg-prices state 計算折扣並顯示

**刷新流程（更新資料）**
1. 使用者點擊「刷新資料」按鈕（本地部署，無需授權）
2. 前端呼叫 `POST /api/refresh?district=XX`
3. 後端爬取司法院拍賣公告（該區）
4. 對每筆地址先正規化（移除樓層、室號等後綴），再查 SQLite geocode 快取
5. 快取未命中才呼叫 Google Geocoding API 取得座標
6. 呼叫內政部實價登錄 API 取得區域均價
7. 將所有資料存入 SQLite，回傳完成狀態與更新筆數
8. 前端重新載入該區資料

**收藏流程**
- 收藏資料儲存在 `localStorage`（key: `favorites`，value: property id 陣列）
- 切換到收藏列表時，前端從 localStorage 讀取 id 清單，並從已載入的 properties state 篩選顯示
- 若切換區域，收藏清單不受影響（跨區收藏由 localStorage 保存）
- 若收藏的物件不在當前已載入的資料中，前端呼叫 `/api/properties/{id}` 補取

---

## 資料庫結構

### `properties` 表
```sql
id            INTEGER PRIMARY KEY
case_number   TEXT UNIQUE       -- 案號（用於 upsert）
court         TEXT              -- 執行法院
district      TEXT              -- 台北市區域（大安區、信義區...）
address       TEXT              -- 原始地址（完整）
address_norm  TEXT              -- 正規化地址（用於 geocode 快取查詢）
lat           REAL              -- 緯度（Geocoding 結果）
lng           REAL              -- 經度（Geocoding 結果）
floor_price   INTEGER           -- 底價（元）
area          REAL              -- 面積（坪）
property_type TEXT              -- 正規化類型（住宅/商辦/土地/其他）
auction_count INTEGER           -- 拍次（第幾拍）
auction_date  DATE              -- 拍賣日期
auction_url   TEXT              -- 司法院公告連結
created_at    DATETIME
updated_at    DATETIME
```

### `avg_prices` 表
```sql
id            INTEGER PRIMARY KEY
district      TEXT
property_type TEXT
avg_price     REAL              -- 均價（萬/坪）
sample_count  INTEGER           -- 樣本數
updated_at    DATETIME
UNIQUE(district, property_type) -- 確保 upsert 正確
```

### `cache_meta` 表
```sql
district      TEXT PRIMARY KEY
last_refreshed_at  DATETIME    -- 最後刷新時間，供 UI 顯示
```

---

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/properties` | 查詢法拍屋列表，支援篩選參數 |
| GET | `/api/properties/{id}` | 取得單一物件詳情（收藏補取用） |
| GET | `/api/avg-prices` | 取得區域實價登錄均價 |
| POST | `/api/refresh` | 觸發重爬 + 更新 SQLite（本地部署，無需授權） |

### GET `/api/properties` 查詢參數
- `district` — 區域名稱（必填）
- `min_price` — 底價下限（元）
- `max_price` — 底價上限（元）
- `auction_count` — 拍次（`1`/`2`/`3`/`all`，預設 `all`）
- `property_type` — 物件類型（`住宅`/`商辦`/`土地`/`其他`/`all`，預設 `all`）

### 回應格式（`/api/properties`）
```json
{
  "district": "大安區",
  "total": 12,
  "last_refreshed_at": "2026-03-29T10:30:00",
  "properties": [
    {
      "id": 1,
      "case_number": "113司執字第12345號",
      "court": "臺灣臺北地方法院",
      "address": "台北市大安區敦化南路一段xxx號3樓",
      "lat": 25.0408,
      "lng": 121.5441,
      "floor_price": 12000000,
      "area": 35.7,
      "property_type": "住宅",
      "auction_count": 1,
      "auction_date": "2025-02-21",
      "auction_url": "https://aomp109.judicial.gov.tw/..."
    }
  ]
}
```

### 回應格式（`POST /api/refresh`）
```json
{
  "district": "大安區",
  "scraped": 15,
  "geocoded_new": 8,
  "geocoded_cached": 7,
  "failed_geocode": 0,
  "last_refreshed_at": "2026-03-29T10:30:00"
}
```

---

## 前端 UI

### 版面配置（Layout A）

```
┌─────────────────────────────────────────────────────┐
│  頂部導覽列：Logo + 台北市各區快選按鈕              │
├──────────────────────┬──────────────────────────────┤
│  左側欄（38%）        │  右側地圖（62%）              │
│                      │                               │
│  [區域選擇下拉]       │  Google Maps                  │
│                      │  - 每個法拍屋一個標記          │
│  篩選條件：           │  - 顏色代表拍次               │
│  • 底價範圍           │    藍=1拍、橘=2拍、紅=3拍+    │
│  • 拍次               │                               │
│  • 物件類型           │  點擊標記 → InfoWindow 彈出：  │
│                      │  • 地址                       │
│  均價資訊：           │  • 底價 / 面積                 │
│  💰 均價 88萬/坪      │  • 拍次 / 拍賣日期             │
│  📅 更新於 3/29 10:30 │  • 底價/坪 vs 均價 對比        │
│                      │  • [⭐收藏] [🔗司法院連結]    │
│  物件列表（可捲動）:  │                               │
│  [全部] [收藏] 切換   │  右上角：[🔄 刷新資料] 按鈕   │
│  • 物件卡片           │                               │
│  • 點擊 = 地圖聚焦   │                               │
│    + InfoWindow       │                               │
└──────────────────────┴──────────────────────────────┘
```

### 地圖標記顏色規則
- 🔵 **藍色** — 第 1 拍
- 🟠 **橘色** — 第 2 拍
- 🔴 **紅色** — 第 3 拍以上

### InfoWindow 內容（點擊標記後）
- 地址
- 底價（元）
- 面積（坪）
- 物件類型
- 拍次
- 拍賣日期
- 法院名稱
- 底價/坪 vs 區域住宅均價比較（折扣 %）— 使用已載入的 avg-prices state
- 按鈕：⭐ 收藏、🔗 司法院原始連結

### 收藏功能
- 使用 `localStorage` 儲存，無需後端
- 左側欄提供「全部」/「收藏」切換 tab
- 收藏 tab 顯示 localStorage 中已收藏物件（優先從當前 state 篩選，跨區物件補呼叫 API）

---

## 後端模組

### `scraper.py` — 司法院爬蟲
- 目標網站：司法院拍賣公告 (aomp109.judicial.gov.tw)
- 以 `requests` + `BeautifulSoup` 解析搜尋結果頁（POST form，支援分頁）
- 篩選：台北市 + 指定區域關鍵字
- 解析欄位：案號、法院、地址、底價、面積、原始類型、拍次、拍賣日期、公告連結
- 若網站結構改變或連線失敗，拋出例外並由 FastAPI 回傳 502 錯誤，不清除現有快取

### `property_type_mapper.py` — 物件類型正規化
將司法院原始類型文字對應到固定四類：

| 原始值（含關鍵字） | 正規化值 |
|-------------------|---------|
| 公寓、住宅、套房、大樓 | 住宅 |
| 辦公室、商業、店面、廠辦 | 商辦 |
| 土地、農地、建地 | 土地 |
| 其他（無法對應） | 其他 |

### `geocoder.py` — 地址轉座標
- 地址正規化：移除「幾樓」、「之幾號」後綴，保留街路門號
- 先以 `address_norm` 查 SQLite 快取
- 快取未命中才呼叫 Google Maps Geocoding API
- 失敗時記錄 warning log，lat/lng 設為 NULL，不中斷批次

### `realtime_prices.py` — 實價登錄
- 使用內政部不動產交易實價登錄 Open Data API（無需 API Key，公開端點）
- 查詢指定區域最近一年住宅成交資料，計算平均坪單價
- Upsert 至 `avg_prices` 表（依 UNIQUE(district, property_type) 覆蓋更新）

### `database.py` — SQLite 操作
- 使用 `sqlite3` 標準函式庫
- `properties` upsert 依 `case_number`
- `avg_prices` upsert 依 `UNIQUE(district, property_type)`
- `cache_meta` upsert 依 `district`，更新 `last_refreshed_at`

---

## 目錄結構

```
法拍屋/
├── backend/
│   ├── main.py              # FastAPI 應用程式入口
│   ├── scraper.py           # 司法院爬蟲
│   ├── geocoder.py          # 地址轉座標
│   ├── property_type_mapper.py  # 物件類型正規化
│   ├── realtime_prices.py   # 實價登錄 API
│   ├── database.py          # SQLite 操作
│   ├── data.db              # SQLite 資料庫（gitignore）
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── Sidebar.jsx        # 左側欄（篩選 + 列表）
│   │   │   ├── MapView.jsx        # Google Maps + 標記
│   │   │   ├── PropertyCard.jsx   # 物件卡片
│   │   │   └── FilterPanel.jsx    # 篩選條件
│   │   ├── hooks/
│   │   │   ├── useProperties.js   # API 呼叫 hook
│   │   │   └── useFavorites.js    # localStorage 收藏 hook
│   │   └── main.jsx
│   ├── index.html
│   ├── vite.config.js       # proxy /api → backend:8000
│   └── package.json
└── docs/
    └── superpowers/specs/
```

---

## 環境變數

```
GOOGLE_MAPS_API_KEY=...    # 同時用於：Maps JS (前端) + Geocoding API (後端)
```

### Google Maps API Key 傳遞方式
- 後端讀取環境變數，用於 Geocoding API 呼叫
- 前端透過 Vite 的 `VITE_GOOGLE_MAPS_API_KEY` 環境變數在 build time 注入
- `.env` 檔案不 commit（加入 `.gitignore`）

### CORS
- FastAPI 設定 `CORSMiddleware`，允許 `http://localhost:5173`（Vite dev server）
- Vite `vite.config.js` 設定 `/api` proxy 到 `http://localhost:8000`

---

## 錯誤處理

| 情境 | 處理方式 |
|------|----------|
| 司法院網站無法連線 | 回傳 502，前端顯示錯誤訊息，保留現有快取資料 |
| Geocoding API 失敗（單筆） | lat/lng 設 NULL，記錄 log；前端不在地圖顯示無座標物件，但列表仍顯示 |
| 資料庫尚無資料 | 前端顯示「尚無資料，請點擊刷新」提示 |
| Google Maps API Key 未設定 | Vite build 時警告；地圖顯示錯誤提示 |
| avg-prices 尚未載入時點擊 InfoWindow | 折扣欄位顯示「載入中...」，待 API 回應後更新 |

---

## 不在範圍內

- 使用者帳號系統（收藏僅用 localStorage）
- 自動排程刷新（手動刷新即可）
- 非台北市的資料
- 行動裝置優化（桌面版優先）
- `/api/refresh` 存取控制（本地部署，不對外暴露）
