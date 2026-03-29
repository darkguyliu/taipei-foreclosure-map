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
