"""
Fetches district average prices from 內政部不動產交易實價登錄 Open Data API.
API docs: https://plvr.land.moi.gov.tw/DownloadOpenData
No API key required.
"""
import logging
import requests
from typing import List, Dict
from property_type_mapper import normalize_property_type
from collections import defaultdict

logger = logging.getLogger(__name__)

# 內政部實價登錄 Open Data endpoint (CSV/JSON for recent transactions)
_API_URL = (
    "https://plvr.land.moi.gov.tw/DownloadSeason"
    "?type=json&fileName=a_lvr_land_a.json"
)

_SQM_TO_PING = 3.30579  # 1 坪 = 3.30579 平方公尺


def fetch_avg_prices(district: str) -> List[Dict]:
    """
    Return list of {property_type, avg_price (萬/坪), sample_count} for district.
    Falls back to empty list on any error.
    """
    try:
        resp = requests.get(_API_URL, timeout=30)
        resp.raise_for_status()
        records = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch avg prices: %s", exc)
        return []

    buckets: Dict[str, List[float]] = defaultdict(list)
    for rec in records:
        if rec.get("鄉鎮市區") != district:
            continue
        raw_type = rec.get("建物型態", "")
        unit_price_sqm = rec.get("單價元平方公尺", "")
        if not unit_price_sqm:
            continue
        try:
            price_sqm = float(unit_price_sqm)
        except ValueError:
            continue
        normalized = normalize_property_type(raw_type)
        price_ping = price_sqm * _SQM_TO_PING / 10_000  # convert to 萬/坪
        buckets[normalized].append(price_ping)

    results = []
    for property_type, prices in buckets.items():
        results.append({
            "property_type": property_type,
            "avg_price": round(sum(prices) / len(prices), 1),
            "sample_count": len(prices),
        })
    return results
