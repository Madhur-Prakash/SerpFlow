"""What real SerpApi responses and real intents look like, as opposed to the mock.

Found by running against live SerpApi: a "no results" answer is billed, and a
conversational intent is not a valid Google Finance query.
"""

from __future__ import annotations

import pytest

from app.core.text import adapt_query, extract_location_phrase, finance_query
from app.integrations.serpapi.client import SerpApiResponse


def _response(payload: dict, status: int = 200) -> SerpApiResponse:
    return SerpApiResponse(payload=payload, http_status=status, latency_ms=1.0)


def test_no_results_is_a_billed_empty_result_not_an_error():
    response = _response(
        {
            "search_metadata": {"id": "abc", "status": "Success"},
            "error": "Google Finance hasn't returned any results for this query.",
        }
    )
    assert response.is_empty_result
    assert not response.is_error


def test_no_results_wording_counts_even_without_metadata():
    response = _response({"error": "Google hasn't returned any results for this query."})
    assert response.is_empty_result
    assert not response.is_error


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"search_metadata": {"status": "Error"}, "error": "Invalid engine."}, 200),
        ({"error": "Missing query `q` parameter."}, 400),
        ({"error": "Google hasn't returned any results for this query."}, 500),
    ],
)
def test_real_errors_stay_errors(payload, status):
    response = _response(payload, status)
    assert not response.is_empty_result
    assert response.is_error


def test_successful_response_is_neither():
    response = _response({"search_metadata": {"status": "Success"}, "organic_results": [{}]})
    assert not response.is_empty_result
    assert not response.is_error


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("nvidia trading at right now", "NVDA:NASDAQ"),
        ("what is the apple share price today", "AAPL:NASDAQ"),
        ("berkshire hathaway stock", "BRK.B:NYSE"),
        ("price of BTC-USD right now", "BTC-USD"),
        ("quote for NVDA:NASDAQ", "NVDA:NASDAQ"),
        ("how is the s&p 500 doing", ".INX:INDEXSP"),
        ("tata steel share price", "tata steel"),
    ],
)
def test_finance_query_produces_an_identifier(text, expected):
    assert finance_query(text) == expected


def test_adapter_only_reshapes_engines_that_need_it():
    assert adapt_query("google_finance", "nvidia trading at right now") == "NVDA:NASDAQ"
    assert adapt_query("google", "nvidia trading at right now") == "nvidia trading at right now"
    assert adapt_query("google_finance", None) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("what is nvidia trading at right now", None),
        ("at least three ramen shops in Kyoto", "Kyoto"),
        ("cafes in Koramangala", "Koramangala"),
        ("hotels near Shibuya at the moment", "Shibuya"),
    ],
)
def test_temporal_phrases_are_not_locations(text, expected):
    assert extract_location_phrase(text) == expected


async def _chosen(intent: str) -> list[str]:
    from app.integrations.llm.mock import MockLLMAdapter
    from app.services.catalog.loader import load_catalog
    from app.services.planner import retrieval

    candidates = retrieval.retrieve(load_catalog(), intent)
    selection = await MockLLMAdapter().select_engines(
        intent, [c.to_payload() for c in candidates], max_select=3
    )
    return [choice.engine for choice in selection.chosen]


async def test_regional_engine_does_not_win_outside_its_market():
    # Naver's description mentions cafes; Koramangala is in Bangalore.
    assert "naver" not in await _chosen("cafes in Koramangala")


async def test_regional_engine_still_wins_in_its_market():
    assert "naver" in await _chosen("best cafes in Seoul")
