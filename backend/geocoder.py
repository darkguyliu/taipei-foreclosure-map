import re
import logging
from typing import Optional, Tuple
import requests

logger = logging.getLogger(__name__)

_FLOOR_PATTERN = re.compile(r"\d+樓(之\d+)?$")
_ROOM_PATTERN = re.compile(r"號之\d+")


def normalize_address(address: str) -> str:
    """Strip floor/unit suffixes, keep street number for geocode cache key."""
    addr = _FLOOR_PATTERN.sub("", address).strip()
    addr = _ROOM_PATTERN.sub("號", addr).strip()
    return addr


def geocode_address(address: str, api_key: str) -> Optional[Tuple[float, float]]:
    """Return (lat, lng) for address via Google Geocoding API, or None on failure."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        resp = requests.get(url, params={"address": address, "key": api_key}, timeout=10)
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
        logger.warning("Geocode failed for '%s': status=%s", address, data.get("status"))
        return None
    except Exception as exc:
        logger.warning("Geocode exception for '%s': %s", address, exc)
        return None
