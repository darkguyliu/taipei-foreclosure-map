import pytest
from scraper import (
    parse_auction_rows, _parse_auction_count, _parse_auction_date, scrape_district,
    _extract_address_fallback,
)

SAMPLE_HTML = """
<table><tr><td>12下一頁</td></tr></table>
<table>
  <tr>
    <th>No</th><th>案號</th><th>拍賣日時</th><th>拍賣註記</th>
    <th>是否點交</th><th>拍定日期</th><th>說明</th><th>環景圖</th><th>污染</th>
  </tr>
  <tr>
    <td>1</td>
    <td>1060100008317(台北分署／申股)</td>
    <td>2021/11/02 15:00:00第三拍</td>
    <td></td>
    <td>Y</td>
    <td>110/11/0244,129,999</td>
    <td>
      一、公告拍賣臺北市大安區信義路三段186號5樓房屋
      <a href="/File/Download?PATH=abc&NAME=test.pdf&DOWNLOAD=公告.pdf">公告</a>
      地號：地址/完整地號：
      <a href="https://www.google.com.tw/maps/place/臺北市大安區信義路三段186號5樓">臺北市大安區信義路三段186號5樓</a>
      底價：37,700,000面積：119.72平方公尺面積：39.51坪
    </td>
    <td></td>
    <td>查詢</td>
  </tr>
  <tr>
    <td>2</td>
    <td>1050100039268(台北分署／亥股)</td>
    <td>2025/01/07 15:00:00特別變賣程序後之拍賣(四拍)</td>
    <td>甲標</td>
    <td>N</td>
    <td>114/01/0783,700,000</td>
    <td>
      本件限採通訊投標
      <a href="/File/Download?PATH=xyz&NAME=doc.pdf&DOWNLOAD=公告.pdf">本件限採通訊投標</a>
      地號：地址/完整地號：
      <a href="https://www.google.com.tw/maps/place/仁愛路四段345巷5弄9號地下室">仁愛路四段345巷5弄9號地下室</a>
      底價：1,386,000面積：1766.54平方公尺面積：534.38坪
    </td>
    <td></td>
    <td>查詢</td>
  </tr>
</table>
<table><tr><td>12下一頁</td></tr></table>
"""


def test_parse_returns_correct_count():
    rows = parse_auction_rows(SAMPLE_HTML, district="大安區")
    assert len(rows) == 2


def test_parse_extracts_fields():
    rows = parse_auction_rows(SAMPLE_HTML, district="大安區")
    row = rows[0]
    assert row["case_number"] == "1060100008317"
    assert row["court"] == "台北分署／申股"
    assert row["address"] == "臺北市大安區信義路三段186號5樓"
    assert row["floor_price"] == 37_700_000
    assert row["area"] == pytest.approx(39.51, abs=0.01)
    assert row["auction_count"] == 3
    assert row["auction_date"] == "2021-11-02"
    assert "/File/Download" in row["auction_url"]


def test_parse_extracts_special_auction():
    rows = parse_auction_rows(SAMPLE_HTML, district="大安區")
    row = rows[1]
    assert row["auction_count"] == 4
    assert row["floor_price"] == 1_386_000
    assert row["area"] == pytest.approx(534.38, abs=0.01)


def test_parse_auction_count_variants():
    assert _parse_auction_count("2021/11/02 15:00:00第一拍") == 1
    assert _parse_auction_count("2021/11/02 15:00:00第二拍") == 2
    assert _parse_auction_count("2021/11/02 15:00:00第三拍") == 3
    assert _parse_auction_count("特別變賣程序後之拍賣(四拍)") == 4
    assert _parse_auction_count("2021/11/02 15:00:00第五拍") == 5
    assert _parse_auction_count("2021/11/02 15:00:00第六拍") == 6
    assert _parse_auction_count("2021/11/02 15:00:00第七拍") == 7
    assert _parse_auction_count("2021/11/02 15:00:00第十拍") == 10
    assert _parse_auction_count("2021/11/02 15:00:00第十一拍") == 11
    assert _parse_auction_count("2021/11/02 15:00:00第十二拍") == 12
    assert _parse_auction_count("2021/11/02 15:00:00第二十拍") == 20
    assert _parse_auction_count("2021/11/02 15:00:00第12拍") == 12


def test_parse_auction_date():
    assert _parse_auction_date("2021/11/02 15:00:00第三拍") == "2021-11-02"
    assert _parse_auction_date("2025/01/07 15:00:00特別變賣") == "2025-01-07"


def test_parse_infers_new_taipei_prefix_from_district():
    rows = parse_auction_rows(SAMPLE_HTML, district="板橋區")
    # Row without an explicit city prefix in the source HTML gets 新北市, not 台北市
    assert rows[1]["address"] == "新北市板橋區仁愛路四段345巷5弄9號地下室"


def test_parse_keeps_existing_city_prefix():
    rows = parse_auction_rows(SAMPLE_HTML, district="板橋區")
    # Row that already carries a 臺北市 prefix in the source HTML is left untouched
    assert rows[0]["address"] == "臺北市大安區信義路三段186號5樓"


def test_scrape_district_unknown_district_returns_empty():
    assert scrape_district("不存在區") == []


NO_MAPS_LINK_HTML = """
<table>
  <tr>
    <th>No</th><th>案號</th><th>拍賣日時</th><th>拍賣註記</th>
    <th>是否點交</th><th>拍定日期</th><th>說明</th><th>環景圖</th><th>污染</th>
  </tr>
  <tr>
    <td>1</td>
    <td>1060100008317(台北分署／申股)</td>
    <td>2021/11/02 15:00:00第三拍</td>
    <td></td>
    <td>Y</td>
    <td>110/11/0244,129,999</td>
    <td>
      一、公告拍賣房屋
      地址/完整地號：臺北市大安區信義路三段186號5樓
      底價：37,700,000面積：119.72平方公尺面積：39.51坪
    </td>
    <td></td>
    <td>查詢</td>
  </tr>
</table>
"""


def test_parse_falls_back_to_text_address_without_maps_link():
    rows = parse_auction_rows(NO_MAPS_LINK_HTML, district="大安區")
    assert len(rows) == 1
    assert rows[0]["address"] == "臺北市大安區信義路三段186號5樓"


LAND_LOT_ONLY_HTML = NO_MAPS_LINK_HTML.replace(
    "地址/完整地號：臺北市大安區信義路三段186號5樓",
    "地址/完整地號：大安段一小段123地號",
)


def test_parse_rejects_land_lot_fallback_without_street_address():
    # A bare 地號 (land lot number) would geocode to the wrong coordinates,
    # so the fallback should reject it rather than return it as an address.
    rows = parse_auction_rows(LAND_LOT_ONLY_HTML, district="大安區")
    assert rows == []


def test_address_fallback_stops_at_trailing_comma():
    # If a comma separates the address from the next field instead of the
    # field label appearing immediately, the match must still terminate at
    # the comma rather than failing outright and losing the row.
    text = "地址/完整地號：臺北市大安區信義路三段186號5樓，底價：100"
    assert _extract_address_fallback(text) == "臺北市大安區信義路三段186號5樓"


def test_address_fallback_rejects_land_lot_with_trailing_text():
    # "地號" in the middle of the candidate (not just at the very end) must
    # still be rejected — e.g. boilerplate like "...地號及其上建物".
    text = "地址/完整地號：大安段一小段123地號及其上建物底價：100"
    assert _extract_address_fallback(text) == ""


def test_parse_ignores_decoy_tables_around_data_table():
    # Extra shell tables (pagination widgets etc.) shouldn't shift which
    # table gets parsed as data, since lookup is now header-driven, not
    # index-based.
    wrapped_html = "<table><tr><td>decoy</td></tr></table>" * 3 + SAMPLE_HTML
    rows = parse_auction_rows(wrapped_html, district="大安區")
    assert len(rows) == 2


def test_parse_matches_header_with_whitespace_between_characters():
    # The live site actually renders the header as "案 號" (space/<br>
    # between characters), not the contiguous "案號" used in the fixtures
    # above — the header match must be whitespace-insensitive or every
    # live query would silently return zero rows.
    html_with_spaced_header = SAMPLE_HTML.replace(
        "<th>案號</th>", "<th>案 號<br>\r\n</th>"
    )
    rows = parse_auction_rows(html_with_spaced_header, district="大安區")
    assert len(rows) == 2
