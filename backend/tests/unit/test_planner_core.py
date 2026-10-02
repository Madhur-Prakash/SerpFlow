"""Unit tests for the planner: pathfinding, candidates, freshness, cost."""

from __future__ import annotations

import pytest

from app.core.text import classify_query, infer_freshness, infer_locale, normalize_dates
from app.integrations.llm.base import FRESHNESS_ORDER, stricter_freshness
from app.services.catalog.graph import apply_fan_out_caps, find_paths
from app.services.catalog.loader import load_catalog, validate_catalog


@pytest.fixture(scope="module")
def index():
    return load_catalog()


# --------------------------------------------------------------------------
# catalog (sections 11, 12)
# --------------------------------------------------------------------------
def test_catalog_has_enough_engines_for_the_demo(index):
    """Section 12: at least 20 engines, including the reference demo chain."""
    assert len(index.engines) >= 20
    for engine in (
        "google_maps",
        "google_maps_reviews",
        "google_maps_contributor_reviews",
    ):
        assert index.has(engine)


def test_catalog_lints_clean(index):
    assert validate_catalog(index) == []


def test_every_engine_has_substitutes_or_states_why(index):
    """Section 11: substitutability is mandatory. An engine with no competitor
    must say so explicitly, so the planner can explain the absence."""
    for name, spec in index.engines.items():
        assert spec.substitutes or spec.single_source_note, name


def test_catalog_has_at_least_two_substitute_groups(index):
    groups = [tag for tag in index.tags() if len(index.by_tag(tag)) > 1]
    assert len(groups) >= 2


def test_substitute_notes_state_a_real_trade_off(index):
    for sub in index.substitutes:
        if not sub.note:
            continue
        # The note is user-facing copy in Plan Inspector rejection reasons.
        assert len(sub.note) > 25, (sub.engine, sub.substitute_engine)


def test_dependency_edges_are_typed_and_resolvable(index):
    for edge in index.edges:
        assert index.has(edge.from_engine)
        assert index.has(edge.to_engine)
        assert edge.satisfies_param in index.get(edge.to_engine).requires


# --------------------------------------------------------------------------
# pathfinding (section 13 stage D)
# --------------------------------------------------------------------------
def test_contributor_chain_is_discovered_by_graph_traversal(index):
    """The discovery proof: the planner reaches an engine with effectively zero
    ecosystem usage through typed edges, not model recall."""
    paths = find_paths(
        index,
        "google_maps_contributor_reviews",
        available_params={"q", "location", "gl", "hl"},
    )
    assert paths
    signatures = {p.signature for p in paths}
    assert "google_maps>google_maps_reviews>google_maps_contributor_reviews" in signatures


def test_full_scale_projection_matches_the_documented_demo_figure(index):
    """Section 70: google_maps 1 + reviews x20 + contributor x80 = 101."""
    paths = find_paths(index, "google_maps_contributor_reviews", available_params={"q", "location"})
    maps_chain = next(p for p in paths if p.engines[0] == "google_maps")
    assert [s.fan_out for s in maps_chain.steps] == [1, 20, 80]
    assert maps_chain.naive_cost == 101


def test_pathfinding_refuses_a_chain_it_cannot_source(index):
    """An engine whose identifier nothing produces and the caller did not supply
    yields no path at all, rather than a guessed one."""
    assert find_paths(index, "google_maps_contributor_reviews", available_params=set()) == []


def test_pathfinding_is_bounded_by_max_hops(index):
    deep = find_paths(index, "google_maps_contributor_reviews", available_params={"q"}, max_hops=1)
    assert deep == []


def test_fan_out_caps_reduce_cost(index):
    path = find_paths(index, "google_maps_contributor_reviews", available_params={"q", "location"})[
        0
    ]
    capped = apply_fan_out_caps(path, {1: 5, 2: 10})
    assert capped.naive_cost < path.naive_cost
    assert capped.steps[1].fan_out == 5
    assert capped.steps[2].fan_out == 10


# --------------------------------------------------------------------------
# locale and freshness inference (section 13 stage C)
# --------------------------------------------------------------------------
def test_seoul_implies_korean_locale():
    """The spec's worked example: Seoul -> gl=kr, hl=ko."""
    locale, matched = infer_locale("recent reviews for a ramen shop in Seoul called Ichiran")
    assert locale.gl == "kr"
    assert locale.hl == "ko"
    assert matched == "seoul"


@pytest.mark.parametrize(
    ("text", "expected_gl"),
    [
        ("cafes in Koramangala", "in"),
        ("restaurants in Tokyo", "jp"),
        ("bakeries in Berlin", "de"),
        ("coffee in Sao Paulo", "br"),
        ("bars in Sydney", "au"),
    ],
)
def test_locale_inference_across_cities(text, expected_gl):
    locale, _ = infer_locale(text)
    assert locale.gl == expected_gl


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("current GOOGL stock price right now", "realtime"),
        ("latest news about the budget", "fresh"),
        ("recent reviews for a cafe", "recent"),
        ("patents filed on lithium anodes", "stable"),
    ],
)
def test_freshness_inference(intent, expected):
    level, signals = infer_freshness(intent, volatility_prior="30d")
    assert level == expected
    assert signals


def test_freshness_signals_name_their_source():
    _, signals = infer_freshness("latest reviews", volatility_prior="7d")
    assert any("temporal language" in s for s in signals)
    assert any("volatility_prior" in s for s in signals)


def test_stricter_freshness_takes_the_tighter_bound():
    assert stricter_freshness("stable", "realtime") == "realtime"
    assert stricter_freshness("fresh", "recent") == "fresh"
    for level in FRESHNESS_ORDER:
        assert stricter_freshness(level, level) == level


def test_volatility_prior_tightens_freshness():
    """An engine whose results move every fifteen minutes cannot serve a
    'stable' answer, whatever the intent's wording implies."""
    relaxed, _ = infer_freshness("patents on lithium anodes", volatility_prior="365d")
    tightened, _ = infer_freshness("patents on lithium anodes", volatility_prior="15m")
    assert relaxed == "stable"
    assert tightened == "realtime"


def test_date_normalization():
    from datetime import date

    out = normalize_dates("flights in late November", today=date(2026, 10, 2))
    assert out["date"] == "2026-11-25"
    assert out["date_qualifier"] == "late"


def test_query_classification():
    assert classify_query("cheapest flight to Hanoi") == "flights"
    assert classify_query("GOOGL share price") == "finance"
    assert classify_query("recent reviews for a cafe") == "reviews"


# --------------------------------------------------------------------------
# Catalog loading failures
# --------------------------------------------------------------------------
def test_a_malformed_engine_names_itself(tmp_path, monkeypatch):
    """A bad catalog must say which engine and which field.

    This reached the API as a bare 500 with no hint once. Tracing it back to a
    single unknown key on one engine took far longer than it should have, so
    the message now carries the file, the engine and the offending field.
    """
    import yaml

    from app.core.exceptions import CatalogError
    from app.services.catalog import loader

    version = tmp_path / "v1"
    version.mkdir()
    (version / "_meta.yaml").write_text(
        yaml.safe_dump(
            {"version": "v1.0.0", "released": "2026-01-01", "source": "x", "capability_tags": {}}
        ),
        encoding="utf-8",
    )
    (version / "engines.yaml").write_text(
        yaml.safe_dump(
            {
                "engines": [
                    {
                        "engine": "google_news",
                        "purpose": "News search.",
                        "capability_tags": ["web_search"],
                        # One key the schema does not know, which is exactly
                        # the shape of the original failure.
                        "requires": {"q": {"type": "string", "caller_suppliabl": True}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(loader, "DATA_ROOT", tmp_path)
    loader.load_catalog.cache_clear()
    try:
        with pytest.raises(CatalogError) as caught:
            loader.load_catalog("v1")
    finally:
        loader.load_catalog.cache_clear()

    message = str(caught.value)
    assert "google_news" in message
    assert "engines.yaml" in message
    assert "caller_suppliabl" in message
    assert caught.value.code == "CATALOG_ERROR"


def test_the_committed_catalog_still_loads():
    """The guard above must not be hiding a real problem in the real catalog."""
    from app.services.catalog.loader import load_catalog

    index = load_catalog()
    assert len(index.engines) == 54
    # The field whose absence caused the original failure.
    assert index.engines["google"].requires["q"].caller_suppliable is True
