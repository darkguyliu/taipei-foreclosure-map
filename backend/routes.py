# backend/routes.py
import logging
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import (
    get_properties, get_avg_prices, get_cache_meta,
    get_property_by_id, upsert_property, upsert_avg_price,
    upsert_cache_meta, get_db,
)
from scraper import scrape_district
from geocoder import normalize_address, geocode_address
from realtime_prices import fetch_avg_prices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


@router.get("/properties")
def list_properties(
    district: str,
    min_price: int = None,
    max_price: int = None,
    auction_count: int = None,
    property_type: str = None,
):
    props = get_properties(district, min_price, max_price, auction_count, property_type)
    meta = get_cache_meta(district)
    return {
        "district": district,
        "total": len(props),
        "last_refreshed_at": meta["last_refreshed_at"] if meta else None,
        "properties": props,
    }


@router.get("/properties/{property_id}")
def get_property(property_id: int):
    prop = get_property_by_id(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.get("/avg-prices")
def avg_prices(district: str):
    prices = get_avg_prices(district)
    return {"district": district, "avg_prices": prices}


@router.post("/refresh")
def refresh(district: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_refresh, district)
    return {"status": "started", "district": district}


def _run_refresh(district: str) -> None:
    logger.info("Starting refresh for %s", district)
    # 1. Scrape
    rows = scrape_district(district)

    # 2. Geocode + normalize + persist
    geocoded_new = geocoded_cached = failed = 0
    for row in rows:
        addr_norm = normalize_address(row["address"])
        row["address_norm"] = addr_norm

        # Check geocode cache via existing properties
        with get_db() as conn:
            cached = conn.execute(
                "SELECT lat, lng FROM properties WHERE address_norm = ? AND lat IS NOT NULL LIMIT 1",
                (addr_norm,),
            ).fetchone()

        if cached:
            row["lat"], row["lng"] = cached["lat"], cached["lng"]
            geocoded_cached += 1
        elif GOOGLE_API_KEY:
            result = geocode_address(addr_norm, GOOGLE_API_KEY)
            if result:
                row["lat"], row["lng"] = result
                geocoded_new += 1
            else:
                row["lat"] = row["lng"] = None
                failed += 1
        else:
            row["lat"] = row["lng"] = None
            failed += 1

        upsert_property(row)

    # 3. Fetch avg prices
    avg_price_list = fetch_avg_prices(district)
    for entry in avg_price_list:
        upsert_avg_price(district, entry["property_type"], entry["avg_price"], entry["sample_count"])

    # 4. Update cache meta
    upsert_cache_meta(district)
    logger.info(
        "Refresh done for %s: scraped=%d new_geocode=%d cached=%d failed=%d",
        district, len(rows), geocoded_new, geocoded_cached, failed,
    )
