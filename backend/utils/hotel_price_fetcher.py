import httpx
import os
from typing import Optional, Tuple
from utils.debug_logger import debug_logger, LogLevel

MAKCORPS_API_KEY = os.getenv("MAKCORPS_API_KEY", "")
MAPPING_URL = "https://api.makcorps.com/mapping"
HOTEL_SEARCH_URL = "https://api.makcorps.com/hotelsearch"
TIMEOUT = 10.0


async def _get_hotel_id(hotel_name: str, region: str) -> Optional[str]:
    """Sucht Hotel-ID via Mapping API. Gibt None zurück wenn nicht gefunden."""
    if not MAKCORPS_API_KEY:
        return None
    search_term = f"{hotel_name} {region}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                MAPPING_URL,
                params={"api_key": MAKCORPS_API_KEY, "name": search_term}
            )
            resp.raise_for_status()
            data = resp.json()
            hotels = [h for h in (data if isinstance(data, list) else []) if h.get("type") == "HOTEL"]
            if hotels:
                return hotels[0].get("document_id")
    except Exception:
        pass
    return None


async def fetch_real_price(
    hotel_name: str,
    region: str,
    checkin: str,   # YYYY-MM-DD
    checkout: str,  # YYYY-MM-DD
    adults: int,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Holt echten Booking.com-Preis per Nacht via HotelAPI.co.
    Returns: (price_per_night_chf, hotel_id) oder (None, None) bei Fehler.
    """
    if not MAKCORPS_API_KEY:
        return None, None

    hotel_id = await _get_hotel_id(hotel_name, region)
    if not hotel_id:
        return None, None

    try:
        url = f"{HOTEL_SEARCH_URL}/{hotel_name}/{hotel_id}/{adults}/1/{checkin}/{checkout}"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params={"api_key": MAKCORPS_API_KEY})
            resp.raise_for_status()
            data = resp.json()
            # Suche Booking.com-Preis in vendors-Liste
            vendors = data.get("vendors", []) if isinstance(data, dict) else []
            for v in vendors:
                if "booking" in str(v.get("vendor", "")).lower():
                    price = v.get("price")
                    if price:
                        return float(price), hotel_id
            # Fallback: günstigster Preis aus allen Anbietern
            prices = [v.get("price") for v in vendors if v.get("price")]
            if prices:
                return float(min(prices)), hotel_id
    except Exception:
        pass
    return None, None
