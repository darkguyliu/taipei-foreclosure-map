# backend/routes.py
import logging
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import (
    get_properties, get_avg_prices, get_cache_meta,
    get_property_by_id, upsert_property, upsert_avg_price,
    upsert_cache_meta, get_geocode_cache,
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
    # This runs as a FastAPI BackgroundTask with no caller to propagate to,
    # so uncaught exceptions here would otherwise vanish silently.
    logger.info("Starting refresh for %s", district)

    # 1. Scrape. A total failure here (CAPTCHA/network) means there's nothing
    # to persist, so abort without touching cache_meta.
    try:
        rows = scrape_district(district)
    except Exception:
        logger.exception("Scrape failed for %s; refresh aborted", district)
        return

    # 2. Geocode + normalize + persist, one row at a time so a single bad
    # row (e.g. a geocoding/DB error) doesn't abort the whole batch and
    # leave avg prices and cache_meta stale relative to what did persist.
    geocode_cache = get_geocode_cache()
    geocoded_new = geocoded_cached = failed = errored = 0
    for row in rows:
        try:
            addr_norm = normalize_address(row["address"])
            row["address_norm"] = addr_norm

            cached = geocode_cache.get(addr_norm)
            if cached:
                row["lat"], row["lng"] = cached
                geocoded_cached += 1
            elif GOOGLE_API_KEY:
                result = geocode_address(addr_norm, GOOGLE_API_KEY)
                if result:
                    row["lat"], row["lng"] = result
                    geocode_cache[addr_norm] = result
                    geocoded_new += 1
                else:
                    row["lat"] = row["lng"] = None
                    failed += 1
            else:
                row["lat"] = row["lng"] = None
                failed += 1

            upsert_property(row)
        except Exception:
            errored += 1
            logger.exception(
                "Failed to process row %s for %s", row.get("case_number"), district,
            )

    # 3. Fetch avg prices (best-effort; a failure here shouldn't hide that
    # properties above were still successfully refreshed).
    try:
        avg_price_list = fetch_avg_prices(district)
        for entry in avg_price_list:
            upsert_avg_price(district, entry["property_type"], entry["avg_price"], entry["sample_count"])
    except Exception:
        logger.exception("Failed to update avg prices for %s", district)

    # 4. Update cache meta — but not if every single row errored out, or a
    # fully-broken refresh (e.g. DB locked, geocoding API down) would mark
    # the district as freshly updated and block retries until the TTL
    # expires, even though nothing was actually persisted.
    if not rows or errored < len(rows):
        upsert_cache_meta(district)
    else:
        logger.error(
            "All %d scraped rows failed to process for %s; not updating cache_meta",
            len(rows), district,
        )
    logger.info(
        "Refresh done for %s: scraped=%d new_geocode=%d cached=%d failed=%d errored=%d",
        district, len(rows), geocoded_new, geocoded_cached, failed, errored,
    )
