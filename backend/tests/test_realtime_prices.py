from unittest.mock import patch, MagicMock
from realtime_prices import fetch_avg_prices


def _csv_response(rows):
    header = "鄉鎮市區,建物型態,單價元平方公尺"
    english_placeholder_row = "The villages and towns urban district,building state,the unit price"
    lines = [header, english_placeholder_row] + [
        f"{r['鄉鎮市區']},{r['建物型態']},{r['單價元平方公尺']}" for r in rows
    ]
    body = "\n".join(lines).encode("utf-8-sig")
    return MagicMock(content=body, raise_for_status=lambda: None)


MOCK_ROWS = [
    {"鄉鎮市區": "大安區", "建物型態": "住宅大樓", "單價元平方公尺": "265000"},
    {"鄉鎮市區": "大安區", "建物型態": "住宅大樓", "單價元平方公尺": "280000"},
    {"鄉鎮市區": "大安區", "建物型態": "辦公商業大樓", "單價元平方公尺": "310000"},
]


def test_fetch_avg_prices_returns_list():
    with patch("realtime_prices.requests.get") as mock_get:
        mock_get.return_value = _csv_response(MOCK_ROWS)
        results = fetch_avg_prices("大安區")
    assert isinstance(results, list)
    assert len(results) >= 1


def test_fetch_avg_prices_calculates_correctly():
    with patch("realtime_prices.requests.get") as mock_get:
        mock_get.return_value = _csv_response(MOCK_ROWS)
        results = fetch_avg_prices("大安區")
    住宅_entry = next((r for r in results if r["property_type"] == "住宅"), None)
    assert 住宅_entry is not None
    # avg of 265000 and 280000 sqm → convert to 坪 (1坪 = 3.30579 sqm)
    # avg_sqm = 272500, per_ping = 272500 * 3.30579 / 10000 ≈ 90.1 萬/坪
    assert 85 < 住宅_entry["avg_price"] < 95
    assert 住宅_entry["sample_count"] == 2


def test_fetch_avg_prices_skips_non_numeric_price_row():
    # A row can match the target district yet still carry a non-numeric price
    # (e.g. malformed feed data) — that specific row must be dropped rather
    # than raising, without affecting the other valid rows for the district.
    rows = MOCK_ROWS + [
        {"鄉鎮市區": "大安區", "建物型態": "住宅大樓", "單價元平方公尺": "not_a_number"},
    ]
    with patch("realtime_prices.requests.get") as mock_get:
        mock_get.return_value = _csv_response(rows)
        results = fetch_avg_prices("大安區")
    total_samples = sum(r["sample_count"] for r in results)
    assert total_samples == len(MOCK_ROWS)


def test_fetch_avg_prices_uses_district_city_file():
    with patch("realtime_prices.requests.get") as mock_get:
        mock_get.return_value = _csv_response([])
        fetch_avg_prices("板橋區")  # 新北市 district
    called_url = mock_get.call_args[0][0]
    assert "fileName=f_lvr_land_a.csv" in called_url


def test_fetch_avg_prices_unknown_district_returns_empty():
    assert fetch_avg_prices("不存在區") == []
