# backend/routes.py
import logging
import os
import threading
import time
from typing import Dict, Optional
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

# Per-district refresh cooldown. Keyed off this dict rather than
# cache_meta.last_refreshed_at, which only updates on success — a
# district that keeps failing to scrape would otherwise never be
# throttled. time.monotonic() because this is pure interval math, immune
# to wall-clock jumps. Process-local: matches running this app as a
# single uvicorn worker (see .claude/launch.json); a multi-worker
# deployment would need a DB-backed lock instead.
MIN_REFRESH_INTERVAL_SECONDS = 5 * 60
_last_attempt: Dict[str, float] = {}

# Caps the rate across *all* districts combined, so a caller can't bypass
# the per-district cooldown by just cycling through every district. No
# per-user/per-IP accounting — fine for trusted/single-user access; would
# need that (and likely auth) before exposing this publicly.
GLOBAL_MIN_INTERVAL_SECONDS = 20
_last_global_attempt: Optional[float] = None

# Districts with a refresh currently running, mapped to when they
# started — guards against two concurrent refreshes of the same district
# double-paying to geocode the same new address. An entry older than
# MAX_REFRESH_DURATION_SECONDS is stale (the BackgroundTask never ran in
# this process) rather than still in progress. Guarded by the same lock
# as _last_attempt so the recency and in-progress checks are one atomic
# step. The duration is set above the worst-case scrape time (PAGE_CAP
# pages * ~35s each, before geocoding) so a merely slow scrape isn't
# mistaken for a stuck one.
MAX_REFRESH_DURATION_SECONDS = 60 * 60
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

    global _last_global_attempt
    now = time.monotonic()
    with _refresh_lock:
        # Checked in order of specificity: is *this* refresh already
        # running (409) before asking whether it's just been refreshed
        # too recently (429) — otherwise the recency check (a full 5
        # minutes) masks the in-progress state for nearly all of a scrape's
        # actual duration, and callers only ever see 409 in the rare case
        # the scrape runs past 5 minutes.
        started_at = _refreshing.get(district)
        if started_at is not None:
            if now - started_at < MAX_REFRESH_DURATION_SECONDS:
                # No Retry-After here: we genuinely don't know how much
                # longer the in-flight refresh has left, and a made-up
                # number (e.g. a flat 60s) would just mislead the caller
                # into waiting the wrong amount of time.
                raise HTTPException(
                    status_code=409,
                    detail="Refresh already in progress for this district",
                )
            # Stale — the previous refresh's entry is being taken over by
            # this request. Logged because it means either a genuinely
            # slow scrape just got raced by a concurrent duplicate, or the
            # prior BackgroundTask never ran at all; worth being able to
            # tell which happened after the fact.
            logger.warning(
                "Stale in-progress entry for %s (%.0fs old); taking it over",
                district, now - started_at,
            )

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

        if _last_global_attempt is not None:
            elapsed = now - _last_global_attempt
            if elapsed < GLOBAL_MIN_INTERVAL_SECONDS:
                retry_after = int(GLOBAL_MIN_INTERVAL_SECONDS - elapsed) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many refresh requests, try again shortly",
                    headers={"Retry-After": str(retry_after)},
                )

        _refreshing[district] = now
        _last_attempt[district] = now
        _last_global_attempt = now

    background_tasks.add_task(_run_refresh_guarded, district, now)
    return {"status": "started", "district": district}


def _run_refresh_guarded(district: str, started_at: float) -> None:
    try:
        _run_refresh(district)
    finally:
        with _refresh_lock:
            # Only clear the entry this call itself created. If it went
            # stale (ran past MAX_REFRESH_DURATION_SECONDS) and a newer
            # request already took the slot, that slot belongs to the new
            # request now — blindly popping here would delete it and let
            # a third request start concurrently with the second.
            if _refreshing.get(district) == started_at:
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
            "Partial scrape for %s (%d rows collected); cache_meta will not be updated",
            district, len(rows),
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
            logger.warning(
                "Failed to normalize address %r for %s",
                row.get("address"), district, exc_info=True,
            )
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
        if addr_norm is None:
            # Already logged with its traceback above, when normalization
            # itself failed — nothing more to add by logging it again here.
            errored += 1
            continue
        try:
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
    if partial:
        pass  # already logged where PartialScrapeError was caught, above
    elif not rows or errored < len(rows):
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
