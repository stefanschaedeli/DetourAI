"""Unit-Tests für MCP-Utility-Module (Brave Search, Weather, Google Places, Wikipedia, Currency)."""
import os
import sys
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _mock_get_session(mock_resp):
    """Erzeugt einen get_session-Mock, der eine Session mit gemocktem .get() zurückgibt."""
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get.return_value = mock_ctx
    return AsyncMock(return_value=mock_session)


# ──────────────── brave_search ────────────────

class TestBraveSearch:
    @pytest.mark.asyncio
    async def test_search_local_no_api_key(self):
        """Ohne API-Key gibt search_local leere Liste zurück."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("BRAVE_API_KEY", None)
            from utils.brave_search import search_local
            result = await search_local("restaurants Annecy France")
            assert result == []

    @pytest.mark.asyncio
    async def test_search_local_with_results(self):
        """Mit API-Key und gültiger Antwort werden strukturierte Ergebnisse zurückgegeben."""
        mock_response = {
            "results": [
                {
                    "title": "Le Bilboquet",
                    "address": {"streetAddress": "14 Rue Sainte-Claire"},
                    "rating": {"ratingValue": 4.5, "ratingCount": 200},
                    "phone": "+33450123456",
                    "priceRange": "€€",
                },
            ]
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        with patch.dict(os.environ, {"BRAVE_API_KEY": "test-key"}):
            with patch("utils.brave_search.get_session", new=_mock_get_session(mock_resp)):
                from utils.brave_search import search_local
                result = await search_local("restaurants Annecy")
                assert len(result) == 1
                assert result[0]["name"] == "Le Bilboquet"
                assert result[0]["rating"] == 4.5

    @pytest.mark.asyncio
    async def test_search_places_fallback(self):
        """search_places fällt auf web search zurück wenn local leer ist."""
        with patch.dict(os.environ, {"BRAVE_API_KEY": "test-key"}):
            with patch("utils.brave_search.search_local", new_callable=AsyncMock, return_value=[]):
                with patch("utils.brave_search.search_web", new_callable=AsyncMock, return_value=[{"name": "Test", "url": "http://test.com", "description": "desc"}]):
                    from utils.brave_search import search_places
                    result = await search_places("test query")
                    assert len(result) == 1
                    assert result[0]["name"] == "Test"

    @pytest.mark.asyncio
    async def test_search_local_error_graceful(self):
        """Bei HTTP-Fehler gibt search_local leere Liste zurück."""
        with patch.dict(os.environ, {"BRAVE_API_KEY": "test-key"}):
            with patch("utils.brave_search.get_session", new=AsyncMock(side_effect=Exception("Connection failed"))):
                from utils.brave_search import search_local
                result = await search_local("test")
                assert result == []


# ──────────────── weather ────────────────

class TestWeather:
    @pytest.mark.asyncio
    async def test_get_forecast_success(self):
        """Wettervorhersage wird korrekt geparst."""
        mock_response = {
            "daily": {
                "time": ["2026-06-01", "2026-06-02"],
                "temperature_2m_max": [25.0, 22.0],
                "temperature_2m_min": [14.0, 12.0],
                "precipitation_sum": [0.0, 5.2],
                "weathercode": [0, 63],
            }
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        with patch("utils.weather.get_session", new=_mock_get_session(mock_resp)):
            from utils.weather import get_forecast
            result = await get_forecast(45.899, 6.129, "2026-06-01", "2026-06-02")
            assert len(result) == 2
            assert result[0]["description"] == "Klar"
            assert result[1]["description"] == "Mässiger Regen"
            assert result[0]["temp_max"] == 25.0
            assert result[1]["precipitation_mm"] == 5.2

    @pytest.mark.asyncio
    async def test_get_forecast_error(self):
        """Bei Fehler gibt get_forecast leere Liste zurück."""
        with patch("utils.weather.get_session", new=AsyncMock(side_effect=Exception("Timeout"))):
            from utils.weather import get_forecast
            result = await get_forecast(0.0, 0.0, "2026-01-01", "2026-01-02")
            assert result == []

    def test_wmo_description(self):
        """WMO-Codes werden korrekt auf deutsche Beschreibungen gemappt."""
        from utils.weather import _wmo_description
        assert _wmo_description(0) == "Klar"
        assert _wmo_description(95) == "Gewitter"
        assert _wmo_description(999) == "Wettercode 999"


# ──────────────── google_places ────────────────

class TestGooglePlaces:
    @pytest.mark.asyncio
    async def test_nearby_search_no_api_key(self):
        """Ohne API-Key gibt nearby_search leere Liste zurück."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_MAPS_API_KEY", None)
            from utils.google_places import nearby_search
            result = await nearby_search(45.9, 6.1, "restaurant")
            assert result == []

    @pytest.mark.asyncio
    async def test_nearby_search_success(self):
        """Nearby Search parst Google Places Antwort korrekt."""
        mock_response = {
            "status": "OK",
            "results": [
                {
                    "place_id": "ChIJ123",
                    "name": "Hotel Alpin",
                    "rating": 4.3,
                    "user_ratings_total": 150,
                    "price_level": 3,
                    "vicinity": "Rue du Lac 5",
                    "geometry": {"location": {"lat": 45.9, "lng": 6.1}},
                    "photos": [{"photo_reference": "ref123"}],
                    "opening_hours": {"open_now": True},
                }
            ],
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-key"}):
            with patch("utils.google_places.get_session", new=_mock_get_session(mock_resp)):
                from utils.google_places import nearby_search
                result = await nearby_search(45.9, 6.1, "lodging")
                assert len(result) == 1
                assert result[0]["name"] == "Hotel Alpin"
                assert result[0]["photo_reference"] == "ref123"
                assert result[0]["rating"] == 4.3

    def test_place_photo_url(self):
        """Photo URL wird korrekt zusammengebaut."""
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-key"}):
            from utils.google_places import place_photo_url
            url = place_photo_url("ref123", max_width=800)
            assert "photoreference=ref123" in url
            assert "maxwidth=800" in url
            assert "key=test-key" in url

    def test_place_photo_url_no_key(self):
        """Ohne Key gibt place_photo_url None zurück."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_MAPS_API_KEY", None)
            from utils.google_places import place_photo_url
            result = place_photo_url("ref123")
            assert result is None


# ──────────────── wikipedia ────────────────

class TestWikipedia:
    @pytest.mark.asyncio
    async def test_get_city_summary_success(self):
        """Wikipedia-Zusammenfassung wird korrekt geparst."""
        mock_response = {
            "title": "Annecy",
            "extract": "Annecy ist eine Stadt in Hochsavoyen...",
            "thumbnail": {"source": "https://upload.wikimedia.org/annecy.jpg"},
            "coordinates": {"lat": 45.899, "lon": 6.129},
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        with patch("utils.wikipedia.get_session", new=_mock_get_session(mock_resp)):
            from utils.wikipedia import get_city_summary
            result = await get_city_summary("Annecy")
            assert result is not None
            assert result["title"] == "Annecy"
            assert "Hochsavoyen" in result["extract"]
            assert result["lat"] == 45.899

    @pytest.mark.asyncio
    async def test_get_city_summary_not_found(self):
        """Bei 404 gibt get_city_summary None zurück."""
        mock_resp = AsyncMock()
        mock_resp.status = 404
        with patch("utils.wikipedia.get_session", new=_mock_get_session(mock_resp)):
            from utils.wikipedia import get_city_summary
            result = await get_city_summary("NonexistentCity12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_city_summary_error(self):
        """Bei Netzwerkfehler gibt get_city_summary None zurück."""
        with patch("utils.wikipedia.get_session", new=AsyncMock(side_effect=Exception("DNS failed"))):
            from utils.wikipedia import get_city_summary
            result = await get_city_summary("Annecy")
            assert result is None


# ──────────────── currency ────────────────

class TestCurrency:
    @pytest.mark.asyncio
    async def test_get_chf_rate_chf(self):
        """CHF → CHF = 1.0."""
        from utils.currency import get_chf_rate
        rate = await get_chf_rate("CHF")
        assert rate == 1.0

    @pytest.mark.asyncio
    async def test_get_chf_rate_fallback(self):
        """Bei Fehler wird Fallback-Kurs verwendet."""
        with patch("utils.currency._fetch_ecb_rates", new_callable=AsyncMock, return_value={}):
            from utils.currency import get_chf_rate, _rate_cache
            _rate_cache.clear()
            rate = await get_chf_rate("EUR")
            assert rate == 0.96  # Fallback

    @pytest.mark.asyncio
    async def test_get_chf_rate_ecb(self):
        """ECB-Kurse werden korrekt in CHF umgerechnet."""
        ecb_rates = {"EUR": 1.0, "CHF": 0.95, "USD": 1.08, "GBP": 0.86}
        with patch("utils.currency._fetch_ecb_rates", new_callable=AsyncMock, return_value=ecb_rates):
            from utils.currency import get_chf_rate, _rate_cache
            _rate_cache.clear()
            rate = await get_chf_rate("EUR")
            # 1 EUR = 0.95 CHF
            assert rate == 0.95

    @pytest.mark.asyncio
    async def test_convert_to_chf(self):
        """Beträge werden korrekt in CHF umgerechnet."""
        with patch("utils.currency.get_chf_rate", new_callable=AsyncMock, return_value=0.95):
            from utils.currency import convert_to_chf
            result = await convert_to_chf(100.0, "EUR")
            assert result == 95.0

    def test_detect_currency(self):
        """Ländernamen werden korrekt auf Währungen gemappt."""
        from utils.currency import detect_currency
        assert detect_currency("Schweiz") == "CHF"
        assert detect_currency("Frankreich") == "EUR"
        assert detect_currency("England") == "GBP"
        assert detect_currency("Norwegen") == "NOK"
        assert detect_currency("Unbekanntes Land") == "EUR"  # Fallback

    @pytest.mark.asyncio
    async def test_rate_caching(self):
        """Kurse werden 24h gecacht."""
        import time
        from utils.currency import _rate_cache, get_chf_rate
        _rate_cache.clear()
        _rate_cache["EUR"] = (0.93, time.time())  # Frischer Cache-Eintrag

        # Sollte Cache verwenden, nicht ECB aufrufen
        with patch("utils.currency._fetch_ecb_rates", new_callable=AsyncMock) as mock_fetch:
            rate = await get_chf_rate("EUR")
            assert rate == 0.93
            mock_fetch.assert_not_called()


# ──────────────── image_fetcher ────────────────

class TestImageFetcher:
    @pytest.mark.asyncio
    async def test_fetch_unsplash_stub(self):
        """fetch_unsplash_images gibt weiterhin Stubs zurück."""
        from utils.image_fetcher import fetch_unsplash_images
        result = await fetch_unsplash_images("Annecy", "restaurant")
        assert result == {"image_overview": None, "image_mood": None, "image_customer": None}

    @pytest.mark.asyncio
    async def test_fetch_place_images_no_place_id(self):
        """fetch_place_images ohne place_id gibt Stubs zurück."""
        from utils.image_fetcher import fetch_place_images
        result = await fetch_place_images("")
        assert result["image_overview"] is None
