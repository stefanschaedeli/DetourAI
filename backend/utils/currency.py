"""Currency conversion utilities — ECB exchange rates to CHF with 24h caching."""
import time
import aiohttp
import xml.etree.ElementTree as ET
from typing import Optional

from utils.http_session import get_session

# Cache: {currency: (rate_to_chf, timestamp)}
_rate_cache: dict[str, tuple[float, float]] = {}
_CACHE_TTL = 86400  # 24h in seconds

# Fallback rates (approximate as of 2025) used when ECB feed is unavailable
_FALLBACK_RATES: dict[str, float] = {
    "CHF": 1.0,
    "EUR": 0.96,   # 1 EUR ≈ 0.96 CHF
    "USD": 0.88,
    "GBP": 1.13,
    "SEK": 0.083,
    "NOK": 0.082,
    "DKK": 0.129,
    "CZK": 0.038,
    "PLN": 0.224,
    "HUF": 0.0024,
    "HRK": 0.128,
    "RON": 0.194,
    "BGN": 0.49,
    "ISK": 0.0064,
    "TRY": 0.027,
}

# Country name (German and English) → ISO 4217 currency code
_COUNTRY_CURRENCY: dict[str, str] = {
    "Schweiz": "CHF", "Switzerland": "CHF",
    "Frankreich": "EUR", "France": "EUR",
    "Deutschland": "EUR", "Germany": "EUR",
    "Österreich": "EUR", "Austria": "EUR",
    "Italien": "EUR", "Italy": "EUR",
    "Spanien": "EUR", "Spain": "EUR",
    "Portugal": "EUR",
    "Niederlande": "EUR", "Netherlands": "EUR",
    "Belgien": "EUR", "Belgium": "EUR",
    "Luxemburg": "EUR", "Luxembourg": "EUR",
    "Griechenland": "EUR", "Greece": "EUR",
    "Irland": "EUR", "Ireland": "EUR",
    "Finnland": "EUR", "Finland": "EUR",
    "Slowenien": "EUR", "Slovenia": "EUR",
    "Slowakei": "EUR", "Slovakia": "EUR",
    "Estland": "EUR", "Estonia": "EUR",
    "Lettland": "EUR", "Latvia": "EUR",
    "Litauen": "EUR", "Lithuania": "EUR",
    "Malta": "EUR",
    "Zypern": "EUR", "Cyprus": "EUR",
    "Kroatien": "EUR", "Croatia": "EUR",
    "England": "GBP", "Grossbritannien": "GBP", "United Kingdom": "GBP",
    "Schweden": "SEK", "Sweden": "SEK",
    "Norwegen": "NOK", "Norway": "NOK",
    "Dänemark": "DKK", "Denmark": "DKK",
    "Tschechien": "CZK", "Czech Republic": "CZK", "Czechia": "CZK",
    "Polen": "PLN", "Poland": "PLN",
    "Ungarn": "HUF", "Hungary": "HUF",
    "Rumänien": "RON", "Romania": "RON",
    "Bulgarien": "BGN", "Bulgaria": "BGN",
    "Island": "ISK", "Iceland": "ISK",
    "Türkei": "TRY", "Turkey": "TRY", "Türkiye": "TRY",
    "USA": "USD", "Vereinigte Staaten": "USD", "United States": "USD",
}


async def _fetch_ecb_rates() -> dict[str, float]:
    """Fetch EUR-based exchange rates from the ECB daily XML feed (free, no API key required).

    Returns a dict mapping currency code to EUR-relative rate, or an empty dict on failure.
    """
    try:
        session = await get_session()
        async with session.get(
            "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return {}
            text = await resp.text()
            root = ET.fromstring(text)
            ns = {"ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
            rates = {"EUR": 1.0}
            for cube in root.findall(".//ecb:Cube[@currency]", ns):
                currency = cube.get("currency", "")
                rate = cube.get("rate", "")
                if currency and rate:
                    rates[currency] = float(rate)
            return rates
    except Exception:
        return {}


async def get_chf_rate(currency: str = "EUR") -> float:
    """Return the exchange rate: 1 {currency} = X CHF. Rates are cached for 24 hours.

    Fetches from ECB on cache miss and converts all rates to CHF-based values.
    Falls back to _FALLBACK_RATES if the ECB feed is unavailable.
    """
    if currency == "CHF":
        return 1.0

    cached = _rate_cache.get(currency)
    if cached and (time.time() - cached[1]) < _CACHE_TTL:
        return cached[0]

    ecb_rates = await _fetch_ecb_rates()
    if ecb_rates and "CHF" in ecb_rates:
        chf_per_eur = ecb_rates["CHF"]
        now = time.time()
        # Convert all ECB EUR-based rates to CHF-based rates and cache them
        for curr, eur_rate in ecb_rates.items():
            if curr != "CHF":
                rate_to_chf = chf_per_eur / eur_rate
                _rate_cache[curr] = (round(rate_to_chf, 6), now)

        cached = _rate_cache.get(currency)
        if cached:
            return cached[0]

    # Fallback
    return _FALLBACK_RATES.get(currency, 1.0)


async def convert_to_chf(amount: float, from_currency: str) -> float:
    """Convert an amount from the given currency to CHF, rounded to 2 decimal places."""
    rate = await get_chf_rate(from_currency)
    return round(amount * rate, 2)


def detect_currency(country: str) -> str:
    """Return the ISO 4217 currency code for a country name (German or English). Defaults to EUR."""
    return _COUNTRY_CURRENCY.get(country, "EUR")
