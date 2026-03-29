"""
Scrapes 司法院拍賣公告 (aomp109.judicial.gov.tw).
The site uses a POST form for search. Results are paginated.
"""
import logging
import re
import requests
from bs4 import BeautifulSoup
from property_type_mapper import normalize_property_type

logger = logging.getLogger(__name__)

BASE_URL = "https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02.htm"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


def _roc_to_ad_date(roc_date: str) -> str:
    """Convert ROC date '114/02/21' to AD '2025-02-21'."""
    parts = roc_date.strip().split("/")
    if len(parts) != 3:
        return roc_date
    year = int(parts[0]) + 1911
    return f"{year}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"


def _parse_price(text: str) -> int:
    """Parse '12,000,000' → 12000000."""
    return int(re.sub(r"[^\d]", "", text))


def _parse_area(text: str) -> float:
    """Parse '35.70坪' → 35.70."""
    match = re.search(r"[\d.]+", text)
    return float(match.group()) if match else 0.0


def parse_auction_rows(html: str, district: str) -> list:
    """Parse table rows from auction result HTML. Only returns rows matching district."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="tableAuction")
    if not table:
        return []

    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue
        address = tds[2].get_text(strip=True)
        if district not in address:
            continue
        link_tag = tds[8].find("a")
        auction_url = f"https://aomp109.judicial.gov.tw{link_tag['href']}" if link_tag else ""
        rows.append({
            "case_number": tds[0].get_text(strip=True),
            "court": tds[1].get_text(strip=True),
            "address": address,
            "property_type": normalize_property_type(tds[3].get_text(strip=True)),
            "area": _parse_area(tds[4].get_text(strip=True)),
            "floor_price": _parse_price(tds[5].get_text(strip=True)),
            "auction_count": int(re.sub(r"[^\d]", "", tds[6].get_text(strip=True)) or 1),
            "auction_date": _roc_to_ad_date(tds[7].get_text(strip=True)),
            "auction_url": auction_url,
            "district": district,
        })
    return rows


def scrape_district(district: str) -> list:
    """
    Fetch all auction listings for a Taipei district.
    Raises requests.RequestException on connection failure (caller handles).
    """
    payload = {
        "cityCode": "63",   # 台北市
        "townCode": "",
        "keyword": district,
        "page": "1",
    }
    all_rows = []
    page = 1
    while True:
        payload["page"] = str(page)
        resp = requests.post(BASE_URL, data=payload, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        rows = parse_auction_rows(resp.text, district)
        all_rows.extend(rows)
        # Stop if last page (no new rows or explicit end marker)
        if not rows:
            break
        page += 1
        if page > 20:  # safety cap
            break
    logger.info("Scraped %d rows for %s", len(all_rows), district)
    return all_rows
