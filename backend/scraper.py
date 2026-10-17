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


def _parse_auction_count(text: str) -> int:
    """Extract auction count from text like '2021/11/02 15:00:00第三拍'."""
    cn_num = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }
    m = re.search(r"第([一二三四五六七八九十\d])拍", text)
    if m:
        ch = m.group(1)
        return cn_num.get(ch, int(ch) if ch.isdigit() else 1)
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


def parse_auction_rows(html: str, district: str, city: str = None) -> list:
    """Parse table rows from query result HTML."""
    city = city or get_city_for_district(district) or "台北市"
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 2:
        return []

    data_table = tables[1]
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
        address = _extract_address(desc_td)
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
        # Fetch a fresh CAPTCHA for every page; the code appears to be
        # single-use/short-lived and reusing it causes later pages to fail.
        captcha_resp = session.get(f"{BASE_URL}/Home/Captcha", timeout=15)
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
        all_rows.extend(rows)

        if not rows:
            break
        page += 1
        if page > 20:  # safety cap
            break

    logger.info("Scraped %d rows for %s", len(all_rows), district)
    return all_rows
