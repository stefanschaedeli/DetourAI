import aiohttp
from typing import Optional

from utils.http_session import get_session

# WMO Weather Code → Deutsche Beschreibung
_WMO_CODES: dict[int, str] = {
    0: "Klar",
    1: "Überwiegend klar",
    2: "Teilweise bewölkt",
    3: "Bedeckt",
    45: "Nebel",
    48: "Reifnebel",
    51: "Leichter Nieselregen",
    53: "Mässiger Nieselregen",
    55: "Starker Nieselregen",
    61: "Leichter Regen",
    63: "Mässiger Regen",
    65: "Starker Regen",
    71: "Leichter Schneefall",
    73: "Mässiger Schneefall",
    75: "Starker Schneefall",
    80: "Leichte Regenschauer",
    81: "Mässige Regenschauer",
    82: "Starke Regenschauer",
    85: "Leichte Schneeschauer",
    86: "Starke Schneeschauer",
    95: "Gewitter",
    96: "Gewitter mit leichtem Hagel",
    99: "Gewitter mit starkem Hagel",
}


def _wmo_description(code: int) -> str:
    return _WMO_CODES.get(code, f"Wettercode {code}")


async def get_forecast(lat: float, lon: float, start_date: str, end_date: str) -> list[dict]:
    """Tägliche Wettervorhersage von Open-Meteo. Kostenlos, kein API-Key nötig.
    start_date/end_date im Format YYYY-MM-DD. Max 16 Tage Vorhersage."""
    try:
        params = {
            "latitude": str(lat),
            "longitude": str(lon),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
            "start_date": start_date,
            "end_date": end_date,
            "timezone": "auto",
        }
        session = await get_session()
        async with session.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            daily = data.get("daily", {})
            dates = daily.get("time", [])
            temps_max = daily.get("temperature_2m_max", [])
            temps_min = daily.get("temperature_2m_min", [])
            precip = daily.get("precipitation_sum", [])
            codes = daily.get("weathercode", [])

            results = []
            for i, d in enumerate(dates):
                results.append({
                    "date": d,
                    "temp_max": temps_max[i] if i < len(temps_max) else None,
                    "temp_min": temps_min[i] if i < len(temps_min) else None,
                    "precipitation_mm": precip[i] if i < len(precip) else None,
                    "weather_code": codes[i] if i < len(codes) else None,
                    "description": _wmo_description(codes[i]) if i < len(codes) else "Unbekannt",
                })
            return results
    except Exception:
        return []


async def get_climate_average(lat: float, lon: float, month: int) -> Optional[dict]:
    """Historische Klima-Durchschnittswerte für einen Standort/Monat.
    Nützlich wenn Reisedatum > 16 Tage entfernt (Vorhersage nicht verfügbar)."""
    try:
        # Open-Meteo Climate API mit ERA5-Daten (30 Jahre Durchschnitt)
        start_date = f"1991-{month:02d}-01"
        end_date = f"2020-{month:02d}-28"
        params = {
            "latitude": str(lat),
            "longitude": str(lon),
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,sunshine_duration",
            "models": "ERA5",
        }
        session = await get_session()
        async with session.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            daily = data.get("daily", {})
            temps_max = [t for t in (daily.get("temperature_2m_max") or []) if t is not None]
            temps_min = [t for t in (daily.get("temperature_2m_min") or []) if t is not None]
            precip = [p for p in (daily.get("precipitation_sum") or []) if p is not None]
            sunshine = [s for s in (daily.get("sunshine_duration") or []) if s is not None]

            avg_temp = round((sum(temps_max) / len(temps_max) + sum(temps_min) / len(temps_min)) / 2, 1) if temps_max and temps_min else None
            avg_rain_days = sum(1 for p in precip if p > 1.0) / max(1, len(precip) // 28) if precip else None
            sunshine_hours = round(sum(sunshine) / 3600 / max(1, len(sunshine) // 28), 1) if sunshine else None

            return {
                "avg_temp": avg_temp,
                "avg_rain_days": round(avg_rain_days, 1) if avg_rain_days else None,
                "sunshine_hours": sunshine_hours,
            }
    except Exception:
        return None
