# backend/routes.py
import logging
import os
import threading
import time
from typing import Dict
from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import (
    get_properties, get_avg_prices, get_cache_meta,
    get_property_by_id, upsert_property, upsert_avg_price,
    upsert_cache_meta, get_geocode_cache,
)
from scraper import scrape_district, PartialScrapeError
from geocoder import normalize_address, geocode_address
from realtime_prices import fetch_avg_prices
from cities import get_city_for_district

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# A refresh scrapes the live site and can call the paid Google Geocoding
# API per new address, so it's throttled per district rather than left
# open to unlimited calls. Tracked here (not via cache_meta.last_refreshed_at)
# because that column is only written on a *successful* refresh — keying
# the throttle off it would mean a district that keeps failing to scrape
# is never actually throttled. This state is process-local: it only
# guards a single uvicorn worker, which matches how this app is run (see
# .claude/launch.json — no --workers flag). A multi-worker deployment
# would need a DB-backed lock instead.
#
# time.monotonic() rather than datetime.now(): this is purely interval
# math (has N seconds passed), and monotonic time can't jump backwards or
# forwards from a wall-clock adjustment (NTP sync, DST, manual change).
MIN_REFRESH_INTERVAL_SECONDS = 5 * 60
_last_attempt: Dict[str, float] = {}

# Districts with a refresh currently running as a BackgroundTask, mapped
# to when they started. Guards against two concurrent refreshes of the
# *same* district each loading their own geocode_cache snapshot and
# re-geocoding (and re-paying for) the same new addresses. An entry older
# than MAX_REFRESH_DURATION_SECONDS is treated as stale rather than still
# "in progress" — if the BackgroundTask never actually ran (e.g. the
# process was killed between accepting the request and running it), the
# district would otherwise be stuck rejecting every refresh until restart.
#
# Guarded by the same lock as _last_attempt so the recency check and the
# in-progress check are one atomic step — otherwise two requests arriving
# close together could both pass the recency check before either one
# takes the in-progress flag.
MAX_REFRESH_DURATION_SECONDS = 30 * 60
_refreshing: Dict[str, float] = {}
_refresh_lock = threading.Lock()


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
    # district is caller-supplied and otherwise unvalidated; without this
    # check, any string writes a cache_meta row for itself via _run_refresh
    # below (scrape_district("不存在區") returns [], which still passes
    # through to upsert_cache_meta).
    if not get_city_for_district(district):
        raise HTTPException(status_code=400, detail="Unknown district")

    now = time.monotonic()
    with _refresh_lock:
        last_attempt = _last_attempt.get(district)
        if last_attempt is not None:
            elapsed = now - last_attempt
            if elapsed < MIN_REFRESH_INTERVAL_SECONDS:
                retry_after = int(MIN_REFRESH_INTERVAL_SECONDS - elapsed) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Refreshed too recently, try again later",
                    headers={"Retry-After": str(retry_after)},
                )

        started_at = _refreshing.get(district)
        if started_at is not None and now - started_at < MAX_REFRESH_DURATION_SECONDS:
            raise HTTPException(
                status_code=429,
                detail="Refresh already in progress for this district",
                headers={"Retry-After": "60"},
            )

        _refreshing[district] = now
        _last_attempt[district] = now

    background_tasks.add_task(_run_refresh_guarded, district)
    return {"status": "started", "district": district}


def _run_refresh_guarded(district: str) -> None:
    try:
        _run_refresh(district)
    finally:
        with _refresh_lock:
            _refreshing.pop(district, None)


def _run_refresh(district: str) -> None:
    # This runs as a FastAPI BackgroundTask with no caller to propagate to,
    # so uncaught exceptions here would otherwise vanish silently.
    logger.info("Starting refresh for %s", district)

    # 1. Scrape. A total failure here (CAPTCHA/network) means there's nothing
    # to persist, so abort without touching cache_meta. A PartialScrapeError
    # still carries whatever rows were collected before pagination broke —
    # those get persisted below, but cache_meta is skipped (see step 4)
    # since later pages may hold rows this refresh never saw.
    partial = False
    try:
        rows = scrape_district(district)
    except PartialScrapeError as exc:
        rows = exc.rows
        partial = True
        logger.warning(
            "Partial scrape for %s (%d rows collected)", district, len(rows),
        )
    except Exception:
        logger.exception("Scrape failed for %s; refresh aborted", district)
        return

    # 2. Geocode + normalize + persist, one row at a time so a single bad
    # row (e.g. a geocoding/DB error) doesn't abort the whole batch and
    # leave avg prices and cache_meta stale relative to what did persist.
    # Addresses are pre-normalized so the geocode cache lookup below can be
    # scoped to just this batch instead of loading every district's history.
    address_norms = []
    for row in rows:
        try:
            address_norms.append(normalize_address(row["address"]))
        except Exception:
            address_norms.append(None)

    try:
        geocode_cache = get_geocode_cache(address_norms)
    except Exception:
        logger.exception(
            "Failed to load geocode cache for %s; proceeding without it", district,
        )
        geocode_cache = {}
    geocoded_new = geocoded_cached = failed = errored = 0
    for row, addr_norm in zip(rows, address_norms):
        try:
            if addr_norm is None:
                raise ValueError(f"Could not normalize address: {row.get('address')!r}")
            row["address_norm"] = addr_norm

            if addr_norm in geocode_cache:
                # Either an existing coordinate loaded from the DB, or one
                # already attempted earlier in this batch (None = failed) —
                # either way, skip hitting the API again for this address.
                cached = geocode_cache[addr_norm]
                if cached:
                    row["lat"], row["lng"] = cached
                    geocoded_cached += 1
                else:
                    row["lat"] = row["lng"] = None
                    failed += 1
            elif GOOGLE_API_KEY:
                result = geocode_address(addr_norm, GOOGLE_API_KEY)
                geocode_cache[addr_norm] = result
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

    # 4. Update cache meta — but not if the scrape was only partial (some
    # later page may hold rows this refresh never saw), nor if every single
    # row raised while being processed (e.g. DB locked). Either case would
    # otherwise mark the district as freshly updated and block retries
    # until the TTL expires, even though the refresh didn't fully succeed.
    # A geocoding failure alone doesn't hit the "all rows failed" path —
    # it's counted in `failed` and the row still persists with lat/lng null.
    if not partial and (not rows or errored < len(rows)):
        upsert_cache_meta(district)
    elif partial:
        logger.error("Refresh for %s was partial; not updating cache_meta", district)
    else:
        logger.error(
            "All %d scraped rows failed to process for %s; not updating cache_meta",
            len(rows), district,
        )
    logger.info(
        "Refresh done for %s: scraped=%d new_geocode=%d cached=%d failed=%d errored=%d",
        district, len(rows), geocoded_new, geocoded_cached, failed, errored,
    )
