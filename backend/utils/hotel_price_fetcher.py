"""
HotelAPI.co / Makcorps Preisabfrage — aktuell deaktiviert.

Die Makcorps Mapping-API (Name → Hotel-ID) ist nicht im kostenlosen Plan enthalten.
Ohne Hotel-ID kann kein echter Preis abgefragt werden.
Der Fallback (Claude-Schätzung + Booking-Link mit Hotelnamen) ist aktiv.

Reaktivierung: Makcorps-Plan mit Mapping-API-Zugang buchen,
dann _get_hotel_id() und fetch_real_price() wieder einschalten.
"""
from typing import Optional, Tuple


async def fetch_real_price(
    hotel_name: str,
    region: str,
    checkin: str,
    checkout: str,
    adults: int,
) -> Tuple[Optional[float], Optional[str]]:
    """Gibt immer (None, None) zurück — Mapping-API nicht verfügbar im Free-Plan."""
    return None, None
