import logging
import pytest
import scraper as scraper_module
from scraper import (
    parse_auction_rows, _parse_auction_count, _parse_auction_date, scrape_district,
    _extract_address_fallback, _cjk_to_int, DataTableNotFoundError,
)


class _FakeResp:
    def __init__(self, json_data=None, text=""):
        self._json = json_data
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        pass


class _FakeSession:
    """Stands in for requests.Session so scrape_district's pagination logic
    can be tested without hitting the real site."""

    def __init__(self):
        self.headers = {}

    def get(self, url, **kwargs):
        if "Captcha" in url:
            return _FakeResp(json_data={"code": "abc"})
        return _FakeResp(text="<html></html>")

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


def test_cjk_to_int_logs_warning_on_unrecognized_token(caplog):
    with caplog.at_level(logging.WARNING, logger="scraper"):
        assert _cjk_to_int("一二") == 1  # mixed digits without 十 — not a real CJK numeral
        assert _cjk_to_int("十十") == 1  # malformed double-十
    assert sum("Unrecognized auction-count token" in r.message for r in caplog.records) == 2


def test_parse_raises_when_no_data_table_found():
    # Distinct from "table found, zero matching rows" (a legitimate empty
    # district) — raising here lets the caller treat it as a scrape
    # failure (skip cache_meta, allow retry) instead of a real empty
    # result, in case the live site's layout changes again.
    with pytest.raises(DataTableNotFoundError):
        parse_auction_rows("<p>not a table at all</p>", district="大安區")


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


def test_scrape_district_keeps_earlier_pages_if_a_later_page_has_no_table(monkeypatch):
    # If the live site's table disappears on page 2+ (e.g. a transient glitch
    # or an edge case this project hasn't seen), pagination should stop and
    # raise PartialScrapeError carrying what page 1 already collected — not
    # discard it, but also not let the caller treat this as a full success
    # (see routes.py's handling: persist .rows, but skip cache_meta).
    monkeypatch.setattr(scraper_module.requests, "Session", _FakeSession)

    page1_rows = [{"case_number": "P1-1"}]
    calls = {"n": 0}

    def _fake_parse(html, district, city=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return page1_rows
        raise DataTableNotFoundError("boom")

    monkeypatch.setattr(scraper_module, "parse_auction_rows", _fake_parse)

    with pytest.raises(scraper_module.PartialScrapeError) as exc_info:
        scraper_module.scrape_district("大安區")
    assert exc_info.value.rows == page1_rows


def test_scrape_district_treats_any_later_page_failure_as_partial(monkeypatch):
    # Not just DataTableNotFoundError — a network timeout, a bad CAPTCHA
    # response, or any other failure on page 2+ must also preserve
    # earlier pages instead of discarding them as a total scrape failure.
    monkeypatch.setattr(scraper_module.requests, "Session", _FakeSession)

    page1_rows = [{"case_number": "P1-1"}]
    calls = {"n": 0}

    def _fake_parse(html, district, city=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return page1_rows
        raise ConnectionError("network blip")

    monkeypatch.setattr(scraper_module, "parse_auction_rows", _fake_parse)

    with pytest.raises(scraper_module.PartialScrapeError) as exc_info:
        scraper_module.scrape_district("大安區")
    assert exc_info.value.rows == page1_rows


def test_scrape_district_raises_if_first_page_has_no_table(monkeypatch):
    # No prior pages to preserve here — this is a real scrape failure, not
    # "the district legitimately has zero listings".
    def _always_raise(html, district, city=None):
        raise DataTableNotFoundError("boom")

    monkeypatch.setattr(scraper_module.requests, "Session", _FakeSession)
    monkeypatch.setattr(scraper_module, "parse_auction_rows", _always_raise)

    with pytest.raises(DataTableNotFoundError):
        scraper_module.scrape_district("大安區")


def test_scrape_district_treats_page_cap_as_partial(monkeypatch):
    # Hitting the 20-page safety cap means there may well be more pages
    # left unread — that's incomplete, not a confirmed full result, so it
    # must raise PartialScrapeError just like a mid-pagination table miss
    # does, rather than silently returning as if nothing were missed.
    monkeypatch.setattr(scraper_module.requests, "Session", _FakeSession)
    monkeypatch.setattr(
        scraper_module, "parse_auction_rows",
        lambda html, district, city=None: [{"case_number": "X"}],  # always another row
    )

    with pytest.raises(scraper_module.PartialScrapeError) as exc_info:
        scraper_module.scrape_district("大安區")
    assert len(exc_info.value.rows) == 20


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


def test_address_fallback_accepts_boulevard_addresses():
    # "大道" (e.g. 市民大道, 凱達格蘭大道) is a common Taipei street type
    # that doesn't contain 路/街/巷/弄 — must not be rejected as a non-address.
    text = "地址/完整地號：臺北市中正區市民大道一段100號底價：100"
    assert _extract_address_fallback(text) == "臺北市中正區市民大道一段100號"


def test_address_fallback_stops_at_other_field_labels():
    # Fields run together with no separator (get_text(strip=True)), so a
    # label other than 底價/面積 immediately following the address must
    # still terminate the match instead of being appended as noise.
    text = "地址/完整地號：臺北市大安區信義路三段186號5樓權利範圍：全部底價：100"
    assert _extract_address_fallback(text) == "臺北市大安區信義路三段186號5樓"


def test_address_fallback_stops_at_additional_known_labels():
    for label in ["坐落", "備註", "車位", "他項權利", "建號", "使用執照"]:
        text = f"地址/完整地號：臺北市大安區信義路三段186號5樓{label}：測試底價：100"
        assert _extract_address_fallback(text) == "臺北市大安區信義路三段186號5樓", label


def test_address_fallback_logs_warning_on_unmatched_label(caplog):
    # A field label not in stop_labels is a known, open-ended limitation.
    # Use filler long enough that no stop point (comma/known label/end of
    # string) falls within the 60-char cap, so the regex finds no match at
    # all — that must at least be logged (at a visible level) so it can be
    # found and added, instead of silently dropping the row with no trace.
    text = "地址/完整地號：" + "甲" * 65 + "底價：100"
    with caplog.at_level(logging.WARNING, logger="scraper"):
        assert _extract_address_fallback(text) == ""
    assert any("didn't match" in r.message for r in caplog.records)


def test_address_fallback_keeps_trailing_号_before_a_label():
    # A trailing 號 followed immediately by a label (no separator) must
    # not be swallowed into that label — the address needs its own 號.
    text = "地址/完整地號：臺北市大安區信義路三段186號5樓用途：住宅底價：100"
    assert _extract_address_fallback(text) == "臺北市大安區信義路三段186號5樓"


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
