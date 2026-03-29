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
