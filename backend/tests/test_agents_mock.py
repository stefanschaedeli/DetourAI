import pytest
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# json_parser
# ---------------------------------------------------------------------------

def test_parse_agent_json_plain():
    from utils.json_parser import parse_agent_json
    raw = '{"stops": [], "total_drive_days": 2}'
    result = parse_agent_json(raw)
    assert result == {"stops": [], "total_drive_days": 2}


def test_parse_agent_json_strips_fences():
    from utils.json_parser import parse_agent_json
    raw = '```json\n{"stops": []}\n```'
    result = parse_agent_json(raw)
    assert result == {"stops": []}


def test_parse_agent_json_strips_plain_fences():
    from utils.json_parser import parse_agent_json
    raw = '```\n{"key": "value"}\n```'
    result = parse_agent_json(raw)
    assert result == {"key": "value"}


def test_parse_agent_json_whitespace():
    from utils.json_parser import parse_agent_json
    raw = '  \n  {"a": 1}  \n  '
    result = parse_agent_json(raw)
    assert result == {"a": 1}


def test_parse_agent_json_invalid():
    from utils.json_parser import parse_agent_json
    with pytest.raises(json.JSONDecodeError):
        parse_agent_json("not json")


# ---------------------------------------------------------------------------
# Route architect — JSON parsing
# ---------------------------------------------------------------------------

def test_route_architect_json_parsing(mocker):
    from models.travel_request import TravelRequest

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"stops": [], "total_drive_days": 2, "total_rest_days": 8, "ferry_crossings": []}')]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    mock_messages = MagicMock()
    mock_messages.create.return_value = mock_response

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    mocker.patch('anthropic.Anthropic', return_value=mock_client)
    mocker.patch('utils.retry_helper.asyncio.to_thread', new=AsyncMock(return_value=mock_response))

    request = TravelRequest(
        start_location="Liestal",
        main_destination="Paris",
        start_date="2026-06-01",
        end_date="2026-06-10",
        total_days=10,
    )

    from agents.route_architect import RouteArchitectAgent
    agent = RouteArchitectAgent(request, "test_job")
    # Verify agent instantiates without errors
    assert agent is not None


# ---------------------------------------------------------------------------
# Retry on rate limit
# ---------------------------------------------------------------------------

def test_retry_on_rate_limit(mocker):
    import asyncio
    from anthropic import RateLimitError
    from utils.retry_helper import call_with_retry

    call_count = 0
    mock_response = MagicMock()

    async def mock_to_thread(fn):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RateLimitError.__new__(RateLimitError)
        return mock_response

    mocker.patch('utils.retry_helper.asyncio.to_thread', side_effect=mock_to_thread)
    mocker.patch('utils.retry_helper.asyncio.sleep', new=AsyncMock())

    # Patch RateLimitError to be catchable
    async def _test():
        result = await call_with_retry(lambda: None, job_id="test", agent_name="test")
        return result

    asyncio.run(_test())
    assert call_count == 2


# ---------------------------------------------------------------------------
# Accommodation researcher — option structure
# ---------------------------------------------------------------------------

def test_accommodation_researcher_instantiation(mocker):
    from models.travel_request import TravelRequest
    from agents.accommodation_researcher import AccommodationResearcherAgent

    mock_client = MagicMock()
    mocker.patch('anthropic.Anthropic', return_value=mock_client)

    request = TravelRequest(
        start_location="Liestal",
        main_destination="Paris",
        start_date="2026-06-01",
        end_date="2026-06-10",
        total_days=10,
        budget_chf=5000,
    )
    agent = AccommodationResearcherAgent(request, "test_job")
    assert agent is not None


# ---------------------------------------------------------------------------
# Activities agent — WikipediaEnricher filter
# ---------------------------------------------------------------------------

def test_wikipedia_enricher_filter():
    from agents.activities_agent import SKIP_PATTERN
    # These should be filtered
    assert SKIP_PATTERN.search("File:Logo_Wikipedia.png")
    assert SKIP_PATTERN.search("File:Flag_of_France.svg")
    assert SKIP_PATTERN.search("File:Icon_map.png")
    # These should pass
    assert not SKIP_PATTERN.search("File:Annecy_Lake.jpg")
    assert not SKIP_PATTERN.search("File:Mont_Blanc_view.jpg")


# ---------------------------------------------------------------------------
# Output generator — instantiation
# ---------------------------------------------------------------------------

def test_output_generator_instantiation():
    from agents.output_generator import OutputGeneratorAgent
    agent = OutputGeneratorAgent()
    assert hasattr(agent, '_create_pdf')
    assert hasattr(agent, '_create_pptx')


# ---------------------------------------------------------------------------
# Maps helper — build_maps_url
# ---------------------------------------------------------------------------

def test_build_maps_url_single():
    from utils.maps_helper import build_maps_url
    url = build_maps_url(["Paris"])
    assert "maps.google.com" in url
    assert "Paris" in url


def test_build_maps_url_multiple():
    from utils.maps_helper import build_maps_url
    url = build_maps_url(["Liestal", "Annecy", "Paris"])
    assert "maps/dir" in url
    assert "Liestal" in url
    assert "Paris" in url
    assert "waypoints" in url


def test_build_maps_url_empty():
    from utils.maps_helper import build_maps_url
    url = build_maps_url([])
    assert url is None


def test_build_maps_url_filters_empty():
    from utils.maps_helper import build_maps_url
    url = build_maps_url(["", "Paris", ""])
    assert url is not None
    assert "Paris" in url


# ---------------------------------------------------------------------------
# Debug logger
# ---------------------------------------------------------------------------

def test_debug_logger_singleton():
    from utils.debug_logger import debug_logger, DebugLogger
    from utils.debug_logger import debug_logger as dl2
    assert debug_logger is dl2


def test_debug_logger_subscribe_unsubscribe():
    import asyncio
    from utils.debug_logger import debug_logger

    async def _run():
        q = debug_logger.subscribe("test_job_123")
        assert q is not None
        debug_logger.unsubscribe("test_job_123")
        assert "test_job_123" not in debug_logger._subscribers

    asyncio.run(_run())
