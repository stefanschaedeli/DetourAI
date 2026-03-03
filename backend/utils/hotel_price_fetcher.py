import httpx
import os
import logging
from typing import Optional, Tuple

MAPPING_URL = "https://api.makcorps.com/mapping"
HOTEL_SEARCH_URL = "https://api.makcorps.com/hotelsearch"
TIMEOUT = 10.0

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """Liest API-Key zur Laufzeit (nicht beim Import), damit .env-Änderungen wirken."""
    return os.getenv("MAKCORPS_API_KEY", "").strip()


async def _get_hotel_id(hotel_name: str, region: str, api_key: str) -> Optional[str]:
    """Sucht Hotel-ID via Mapping API. Gibt None zurück wenn nicht gefunden."""
    search_term = f"{hotel_name} {region}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                MAPPING_URL,
                params={"api_key": api_key, "name": search_term}
            )
            logger.debug("Mapping API %s → %s: %s", search_term, resp.status_code, resp.text[:200])
            resp.raise_for_status()
            data = resp.json()
            hotels = [h for h in (data if isinstance(data, list) else []) if h.get("type") == "HOTEL"]
            if hotels:
                return hotels[0].get("document_id")
            logger.debug("Mapping: kein Hotel gefunden für '%s'", search_term)
    except Exception as e:
        logger.warning("Mapping API Fehler für '%s': %s", search_term, e)
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
    api_key = _get_api_key()
    if not api_key:
        logger.warning("MAKCORPS_API_KEY nicht gesetzt — überspringe Preisabfrage")
        return None, None

    hotel_id = await _get_hotel_id(hotel_name, region, api_key)
    if not hotel_id:
        return None, None

    try:
        url = f"{HOTEL_SEARCH_URL}/{hotel_name}/{hotel_id}/{adults}/1/{checkin}/{checkout}"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params={"api_key": api_key})
            logger.debug("Price API %s → %s: %s", url, resp.status_code, resp.text[:300])
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
            logger.debug("Price API: keine vendors in Antwort für hotel_id=%s", hotel_id)
    except Exception as e:
        logger.warning("Price API Fehler für '%s' (%s): %s", hotel_name, hotel_id, e)
    return None, None
