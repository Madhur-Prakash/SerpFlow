"""The entity/numeral guard and cache key normalisation (section 17).

The guard is the reason a 0.98 cosine score is not enough to serve a cached
result. These tests assert the exact failures the spec names.
"""

from __future__ import annotations

import pytest

from app.integrations.llm.embedding import similarity
from app.services.cache import guard
from app.services.cache.keys import (
    build_key,
    is_identifier_lookup,
    normalize_request,
    request_hash,
)


# --------------------------------------------------------------------------
# the two failures the spec names explicitly
# --------------------------------------------------------------------------
def test_iphone_16_never_matches_iphone_17():
    verdict = guard.check("iphone 16 pro max price", "iphone 17 pro max price")
    assert not verdict.accepted
    assert verdict.reason == guard.REASON_NUMERAL
    assert "16" in verdict.detail or "17" in verdict.detail


def test_koramangala_never_matches_indiranagar():
    verdict = guard.check("restaurants in Koramangala", "restaurants in Indiranagar")
    assert not verdict.accepted
    assert verdict.reason == guard.REASON_ENTITY


def test_a_true_paraphrase_clears_the_threshold():
    """The semantic layer has to be able to fire at all, or it is dead code.
    Word order and stopwords must not move the vector."""
    from app.core.config import settings

    assert (
        similarity("cafes in Koramangala", "Koramangala cafes")
        >= settings.semantic_similarity_threshold
    )


def test_entity_swaps_score_high_but_are_not_the_same_question():
    """A near-miss sits close enough to a real paraphrase that similarity alone
    is not a safe test, which is exactly why the guard exists.

    The deterministic local embedder is deliberately conservative - these pairs
    land in the high 0.8s to low 0.9s rather than the 0.98 a dense sentence
    model would report - so at the default 0.95 threshold they would also be
    filtered by score here. The guard is what keeps that true when the
    embedding model is swapped for a denser one, because it does not consult
    the score at all.
    """
    near_miss = similarity(
        "best rated speciality coffee roasters with outdoor seating wifi parking "
        "and late night hours in Koramangala Bangalore",
        "best rated speciality coffee roasters with outdoor seating wifi parking "
        "and late night hours in Indiranagar Bangalore",
    )
    unrelated = similarity("cheapest flights to Hanoi", "coffee shops in Berlin")
    assert near_miss > 0.85
    assert unrelated < 0.3


def test_the_guard_does_not_consult_the_similarity_score():
    """Section 17: any difference rejects the hit, regardless of cosine score.

    The guard signature takes two query strings and nothing else - there is no
    code path by which a high score could override it.
    """
    import inspect

    assert "similarity" not in inspect.signature(guard.check).parameters
    assert "score" not in inspect.signature(guard.check).parameters


# --------------------------------------------------------------------------
# acceptance
# --------------------------------------------------------------------------
def test_identical_queries_pass():
    verdict = guard.check("cafes in Koramangala", "cafes in Koramangala")
    assert verdict.accepted
    assert verdict.reason == guard.REASON_OK


def test_wording_differences_without_entity_differences_pass():
    verdict = guard.check("cafes in Koramangala", "Koramangala cafes")
    assert verdict.accepted


@pytest.mark.parametrize(
    ("incoming", "candidate", "reason"),
    [
        # s24 / s25 are model identifiers, not bare numerals: there is no word
        # boundary before the digits, so the version family catches them.
        ("galaxy s24 ultra", "galaxy s25 ultra", guard.REASON_VERSION),
        ("python 3.12 release notes", "python 3.13 release notes", guard.REASON_NUMERAL),
        ("weather in Paris", "weather in Berlin", guard.REASON_ENTITY),
        ("top 10 cafes", "top 20 cafes", guard.REASON_NUMERAL),
        ("4K monitor reviews", "8K monitor reviews", guard.REASON_VERSION),
    ],
)
def test_guard_rejects_near_misses(incoming, candidate, reason):
    verdict = guard.check(incoming, candidate)
    assert not verdict.accepted
    assert verdict.reason == reason


def test_guard_is_deterministic():
    """No model is consulted, so the same pair always produces the same verdict."""
    first = guard.check("iphone 16", "iphone 17")
    for _ in range(20):
        assert guard.check("iphone 16", "iphone 17").reason == first.reason


def test_guard_against_stored_tokens_matches_live_extraction():
    tokens = guard.tokens_for_storage("restaurants in Indiranagar")
    verdict = guard.check_against_stored(
        "restaurants in Koramangala",
        tokens["numerals"],
        tokens["entities"],
        tokens["versions"],
        "restaurants in Indiranagar",
    )
    assert not verdict.accepted
    assert verdict.reason == guard.REASON_ENTITY


def test_guard_falls_back_when_stored_tokens_are_absent():
    """Entries written before the token columns existed must still be guarded,
    not silently accepted."""
    verdict = guard.check_against_stored("iphone 16", None, None, None, "iphone 17")
    assert not verdict.accepted


# --------------------------------------------------------------------------
# key normalisation
# --------------------------------------------------------------------------
def test_non_semantic_parameters_do_not_change_the_key():
    """api_key, output and no_cache never change the result, so they must never
    change the cache key."""
    base = {"q": "cafes", "gl": "in"}
    assert request_hash("google", base) == request_hash(
        "google", {**base, "api_key": "secret", "output": "json", "no_cache": "true"}
    )


def test_normalisation_folds_case_and_whitespace():
    assert request_hash("google", {"q": "  Cafes  IN   Koramangala "}) == request_hash(
        "google", {"q": "cafes in koramangala"}
    )


def test_parameter_order_does_not_change_the_key():
    assert request_hash("google", {"q": "x", "gl": "in", "hl": "en"}) == request_hash(
        "google", {"hl": "en", "q": "x", "gl": "in"}
    )


def test_different_engines_get_different_keys():
    assert request_hash("google", {"q": "x"}) != request_hash("bing", {"q": "x"})


def test_normalized_request_keeps_the_engine():
    assert normalize_request("google_maps", {"q": "cafes"})["engine"] == "google_maps"


def test_partition_isolates_projects_by_default():
    a = build_key("google", {"q": "x"}, project_id="prj_a", org_id="org_1")
    b = build_key("google", {"q": "x"}, project_id="prj_b", org_id="org_1")
    assert a.partition != b.partition
    assert a.request_hash == b.request_hash
    assert a.redis_key != b.redis_key


def test_shared_cache_merges_projects_within_one_org():
    a = build_key("google", {"q": "x"}, project_id="prj_a", org_id="org_1", scope="organization")
    b = build_key("google", {"q": "x"}, project_id="prj_b", org_id="org_1", scope="organization")
    assert a.partition == b.partition == "org:org_1"


def test_identifier_lookups_skip_the_semantic_layer():
    """A 'similar' data_id is a different place, so a semantic hit there would
    be a correctness bug rather than a saving."""
    assert is_identifier_lookup("google_maps_reviews", {"data_id": "0xabc:0xdef"})
    assert not is_identifier_lookup("google_maps", {"q": "cafes in Koramangala"})
