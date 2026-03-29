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
