import pytest
from scraper import parse_auction_rows, _parse_auction_count, _parse_auction_date

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


def test_parse_auction_date():
    assert _parse_auction_date("2021/11/02 15:00:00第三拍") == "2021-11-02"
    assert _parse_auction_date("2025/01/07 15:00:00特別變賣") == "2025-01-07"
