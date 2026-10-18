"""
Scrapes 法務部行政執行署拍賣公告查詢系統 (tpkonsale.moj.gov.tw).
Uses GET /Estate/Query with CAPTCHA (code returned in API response).
"""
import logging
import re
import requests
from bs4 import BeautifulSoup
from cities import get_city_for_district, get_county_code, get_area_code, KNOWN_CITY_PREFIXES
from property_type_mapper import normalize_property_type

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tpkonsale.moj.gov.tw"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


_CJK_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CJK_TOKEN_RE = re.compile(r"^(?:[一二三四五六七八九]?十[一二三四五六七八九]?|[一二三四五六七八九])$")


def _cjk_to_int(token: str) -> int:
    """Convert a CJK numeral (1-99) like '三'→3, '十'→10, '十一'→11, '二十'→20 to int.

    Anything not matching that shape (mixed/garbled input like '一二' or
    '十十') is logged and defaults to 1, rather than silently guessing.
    """
    if not _CJK_TOKEN_RE.match(token):
        logger.warning("Unrecognized auction-count token %r, defaulting to 1", token)
        return 1
    if "十" in token:
        tens, _, ones = token.partition("十")
        tens_val = _CJK_DIGITS.get(tens, 1)  # bare "十" means 10, not "0 十"
        ones_val = _CJK_DIGITS.get(ones, 0)
        return tens_val * 10 + ones_val
    return _CJK_DIGITS[token]


def _parse_auction_count(text: str) -> int:
    """Extract auction count from text like '2021/11/02 15:00:00第三拍' or '...第十一拍'."""
    m = re.search(r"第([一二三四五六七八九十\d]+)拍", text)
    if m:
        token = m.group(1)
        return int(token) if token.isdigit() else _cjk_to_int(token)
    if "特別變賣" in text or "四拍" in text:
        return 4
    return 1


def _parse_auction_date(text: str) -> str:
    """Extract date from text like '2021/11/02 15:00:00第三拍' → '2021-11-02'."""
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _extract_address(td) -> str:
    """Extract the address from the description cell's Google Maps link."""
    for a in td.find_all("a"):
        href = a.get("href", "")
        if "google" in href and "maps" in href:
            return a.get_text(strip=True)
    return ""


def _extract_address_fallback(description_text: str) -> str:
    """Fallback address parse straight from the 地址/完整地號 label, used when
    the description has no Google Maps link to pull the address from.

    Bounded to 60 chars and requires a street-address shape (a 路/街/巷/弄/
    大道 marker followed by a 號) while rejecting any candidate that still
    contains 地號 (land lot number, e.g. "OO段123地號及其上建物") — those
    would geocode to the wrong place rather than a real street address.

    get_text(strip=True) runs all description fields together with no
    separator, so the match must also stop at the next known field label
    (not just 底價/面積) or trailing field text gets appended as noise.
    `stop_labels` must be an explicit list, not a generic "N Han chars
    then ：" pattern — the address's own trailing 號 can fuse with the
    next label's first characters into something that looks like one.
    """
    stop_labels = (
        "底價|面積|權利範圍|用途|使用分區|建物|持分|使用現況|點交|稅捐"
        "|坐落|備註|車位|他項權利|建號|使用執照"
    )
    m = re.search(
        rf"地址/完整地號[：:]\s*([^，,。]{{1,60}}?)(?=[，,。]|(?:{stop_labels})[：:]|$)",
        description_text,
    )
    if not m:
        logger.warning(
            "Address fallback didn't match (no known field label after it?"
            " — may need to add a label to stop_labels): %.80s",
            description_text,
        )
        return ""
    candidate = m.group(1).strip()
    if not candidate or "地號" in candidate or not re.search(r"(?:[路街巷弄]|大道).*號", candidate):
        return ""
    return candidate


def _extract_price(description_text: str) -> int:
    """Extract 底價 (reserve price) from description text."""
    m = re.search(r"底價[：:]\s*([\d,]+)", description_text)
    if m:
        return int(re.sub(r"[^\d]", "", m.group(1)))
    return 0


def _extract_area_ping(description_text: str) -> float:
    """Extract area in 坪 from description text."""
    m = re.search(r"面積[：:]\s*([\d,.]+)\s*坪", description_text)
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


def _extract_auction_url(td) -> str:
    """Extract the PDF download link from the description cell."""
    for a in td.find_all("a"):
        href = a.get("href", "")
        if "/File/Download" in href:
            return f"{BASE_URL}{href}"
    return ""


def _extract_sold_price(text: str) -> int:
    """Extract sold price from td[5] text like '110/11/021,396,800'."""
    # Format: ROC-date followed by price digits with commas
    m = re.search(r"\d{3}/\d{2}/\d{2}([\d,]+)", text)
    if m:
        return int(re.sub(r"[^\d]", "", m.group(1)))
    return 0


def _has_city_prefix(address: str) -> bool:
    """Whether the address already starts with any known city name (any 台/臺 variant)."""
    return any(address.startswith(prefix) for prefix in KNOWN_CITY_PREFIXES)


def _find_data_table(tables):
    """Locate the actual results table by its header, rather than assuming a
    fixed table index (surrounding pagination/shell tables can shift).

    The live site renders the header as "案 號" (with whitespace/line breaks
    between characters), so the header text is whitespace-normalized before
    matching — comparing the raw text against "案號" would never match and
    silently return no rows for every query.
    """
    for table in tables:
        header_row = table.find("tr")
        if not header_row or not header_row.find_all("th", recursive=False):
            continue
        header_text = re.sub(r"\s+", "", header_row.get_text())
        if "案號" in header_text:
            return table
    return None


class DataTableNotFoundError(RuntimeError):
    """The results table couldn't be located in the page at all — distinct
    from a found table with zero matching rows, which is a legitimate
    "no listings right now" result. Raised instead of returning [] so a
    site layout change surfaces as a scrape failure (skips cache_meta,
    allows retry) rather than looking identical to a real empty district.
    """


class PartialScrapeError(RuntimeError):
    """Pagination stopped early (page 2+) because the data table couldn't
    be found on a later page. Carries whatever rows were already collected
    via .rows — the caller can still persist them, but should treat the
    scrape as incomplete (e.g. skip cache_meta) rather than fully successful,
    since further rows may exist on the page that failed to parse.
    """

    def __init__(self, rows):
        super().__init__(f"Pagination stopped early with {len(rows)} rows collected")
        self.rows = rows


def parse_auction_rows(html: str, district: str, city: str = None) -> list:
    """Parse table rows from query result HTML."""
    city = city or get_city_for_district(district) or "台北市"
    soup = BeautifulSoup(html, "html.parser")
    data_table = _find_data_table(soup.find_all("table"))
    if data_table is None:
        raise DataTableNotFoundError(
            f"No data table found for {district} (page layout may have changed)"
        )

    rows = []
    for tr in data_table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue

        # td[1]: case number + branch
        case_text = tds[1].get_text(strip=True)
        case_match = re.match(r"(\d+)", case_text)
        case_number = case_match.group(1) if case_match else case_text
        court_match = re.search(r"\((.+?)\)", case_text)
        court = court_match.group(1) if court_match else ""

        # td[2]: auction date + count
        date_count_text = tds[2].get_text(strip=True)
        auction_date = _parse_auction_date(date_count_text)
        auction_count = _parse_auction_count(date_count_text)

        # td[6]: description with address, price, area, PDF link
        desc_td = tds[6]
        desc_text = desc_td.get_text(strip=True)
        address = _extract_address(desc_td) or _extract_address_fallback(desc_text)
        if not address:
            continue

        # Ensure address has city/district prefix for geocoding
        if not _has_city_prefix(address):
            address = f"{city}{district}{address}"

        floor_price = _extract_price(desc_text)
        # Fallback: use sold price from td[5] if no 底價 found
        if floor_price == 0:
            floor_price = _extract_sold_price(tds[5].get_text(strip=True))

        area = _extract_area_ping(desc_text)
        auction_url = _extract_auction_url(desc_td)

        # Determine property type from description
        property_type = normalize_property_type(desc_text)

        rows.append({
            "case_number": case_number,
            "court": court,
            "address": address,
            "property_type": property_type,
            "area": area,
            "floor_price": floor_price,
            "auction_count": auction_count,
            "auction_date": auction_date,
            "auction_url": auction_url,
            "district": district,
        })
    return rows


def scrape_district(district: str) -> list:
    """
    Fetch all auction listings for a district from 法務部行政執行署.
    Supports 台北市 and 新北市 districts (see cities.py).
    """
    city = get_city_for_district(district)
    county_code = get_county_code(district)
    area_code = get_area_code(district)
    if not city or not county_code or not area_code:
        logger.warning("Unknown district: %s", district)
        return []

    session = requests.Session()
    session.headers.update(HEADERS)

    # Visit main page to initialize session
    session.get(f"{BASE_URL}/", timeout=15)

    all_rows = []
    page = 1
    while True:
        try:
            # Fetch a fresh CAPTCHA for every page; the code appears to be
            # single-use/short-lived and reusing it causes later pages to fail.
            captcha_resp = session.get(f"{BASE_URL}/Home/Captcha", timeout=15)
            captcha_resp.raise_for_status()
            captcha_code = captcha_resp.json()["code"]

            params = {
                "COUNTY": county_code,
                "AREA": area_code,
                "CAPTCHA": captcha_code,
                "REQUERY": "false" if page == 1 else "true",
                "PAGINATION_PAGE_NO": str(page),
            }
            resp = session.get(f"{BASE_URL}/Estate/Query", params=params, timeout=20)
            resp.raise_for_status()

            rows = parse_auction_rows(resp.text, district, city)
        except Exception as exc:
            if page == 1:
                raise  # no data at all — a real scrape failure, not "0 results"
            # Already-collected pages are kept, but the caller must not
            # treat this as a fully successful scrape (e.g. for cache_meta)
            # since later pages may hold rows that were never collected.
            # Deliberately broad: a network timeout or bad CAPTCHA response
            # on page 2+ shouldn't discard page 1 either, not just a
            # missing-table parse failure.
            logger.warning(
                "Page %d failed for %s; stopping with %d rows collected",
                page, district, len(all_rows), exc_info=True,
            )
            raise PartialScrapeError(all_rows) from exc

        all_rows.extend(rows)

        if not rows:
            break
        page += 1
        if page > 20:
            # Safety cap — there may well be more pages past this one, so
            # treat it the same as a page breaking mid-pagination: the
            # caller shouldn't mark this district as fully refreshed.
            logger.warning(
                "Hit the 20-page safety cap for %s with %d rows collected",
                district, len(all_rows),
            )
            raise PartialScrapeError(all_rows)

    logger.info("Scraped %d rows for %s", len(all_rows), district)
    return all_rows
