"""End-to-end: the product thesis (sections 76, 83).

    The e2e suite must include an explicit test asserting that cache state
    changed which plan was selected.

A cache hit after the same plan was chosen is NOT sufficient. This test
asserts that the cold-cost ranking and the marginal-cost ranking disagreed, and
that the marginal ranking is what executed.
"""

from __future__ import annotations

import pytest

from app.core import metrics
from app.services import runs as run_service

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

REFERENCE_INTENT = "find coordinated review rings among Koramangala cafes"
DEMO_BUDGET = 20


def _replan_counter_total() -> float:
    total = 0.0
    for metric in metrics.REGISTRY.collect():
        if metric.name != "serpflow_marginal_replan_changed_selection":
            continue
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                total += sample.value
    return total


async def test_marginal_replanning_changes_plan_selection(
    requires_postgres, session, org_fixture, test_principal
):
    """The headline assertion.

    Run one: a cold cache. Run two: the same intent against the warm cache left
    behind by a full-scale run. The selected plan must differ, and the planner
    must have recorded that it differed.
    """
    from app.services.budgets.service import ensure_budget

    org = org_fixture["org"]
    project = org_fixture["project"]
    before = _replan_counter_total()

    # ---- run one: cold --------------------------------------------------
    cold = await run_service.plan_and_execute(
        session,
        principal=test_principal,
        intent=REFERENCE_INTENT,
        project_id=project.id,
        budget=DEMO_BUDGET,
        execute=True,
        trigger="test",
    )
    cold_plan = cold["plan"]
    cold_engines = [s["engine"] for s in cold_plan.steps]

    assert cold["run"].status == "succeeded"
    # Section 13 stage D: candidate plurality is a hard requirement.
    assert cold_plan.candidate_count >= 2, "stage D must emit multiple candidates"
    assert not cold_plan.marginal_replan_changed_selection, (
        "a cold cache has nothing to re-rank on, so the two rankings must agree"
    )
    # Test keys route to the deterministic mock, so nothing was spent.
    assert cold["run"].credits_spent == 0
    assert cold["mode"].label == "MOCK"

    # ---- warm the full chain ---------------------------------------------
    # A second project, whose policy pins the Google Maps corpus, runs the same
    # investigation at full scale against the mock. Its spend warms the shared
    # organization cache.
    from app.services.auth.service import AuthService

    org.cache_scope = "organization"
    project.shared_cache_enabled = True
    auth = AuthService(session)
    warm_project = await auth.create_project(org_id=org.id, name="Warm-up")
    warm_project.shared_cache_enabled = True
    # Pin the map corpus so the warm-up routes through google_maps rather than
    # the cheaper local-pack entry point. That is what makes the second run's
    # cold and marginal rankings disagree.
    warm_project.engine_denylist = ["yelp", "yelp_reviews", "google_local"]
    await ensure_budget(
        session,
        org_id=org.id,
        scope="project",
        scope_id=warm_project.id,
        limit_credits=200,
        name="warm-up budget",
    )
    warm_key_row, _ = await auth.create_api_key(
        org_id=org.id, project=warm_project, name="warm key", environment="test"
    )
    await session.flush()

    from app.core.permissions import permissions_for
    from app.services.auth.service import Principal

    warm_principal = Principal(
        id=warm_key_row.id,
        type="api_key",
        org_id=org.id,
        project_id=warm_project.id,
        role=warm_key_row.role,
        api_key_id=warm_key_row.id,
        key_environment="test",
        permissions=permissions_for(warm_key_row.role),
    )
    warmup = await run_service.plan_and_execute(
        session,
        principal=warm_principal,
        intent=REFERENCE_INTENT,
        project_id=warm_project.id,
        budget=None,
        execute=True,
        trigger="test",
    )
    assert warmup["run"].status == "succeeded"
    assert "google_maps_contributor_reviews" in [s["engine"] for s in warmup["plan"].steps], (
        "the warm-up must route through the contributor chain"
    )

    # ---- run two: same intent, warm cache --------------------------------
    warm = await run_service.plan_and_execute(
        session,
        principal=test_principal,
        intent=REFERENCE_INTENT,
        project_id=project.id,
        budget=DEMO_BUDGET,
        execute=True,
        trigger="test",
    )
    warm_plan = warm["plan"]
    warm_engines = [s["engine"] for s in warm_plan.steps]

    # ---- the assertions that matter --------------------------------------
    assert warm_plan.marginal_replan_changed_selection is True, (
        "cache-aware marginal-cost replanning must have changed the selection"
    )
    assert warm_engines != cold_engines, (
        "same intent, same catalog, different selected plan - the only thing "
        "that changed was cache state"
    )
    assert warm_plan.marginal_cost < warm_plan.naive_cost, (
        "the selected plan must be cheaper on the margin than cold"
    )
    assert warm_plan.warm_steps, "the plan must identify which steps are warm"
    assert warm_plan.replan_explanation
    assert warm_plan.catalog_version == cold_plan.catalog_version

    # The thesis, instrumented (section 65).
    assert _replan_counter_total() > before

    # The counterfactual is persisted, not recomputed by the UI (section 15).
    assert warm_plan.cold_winner_candidate_id is not None
    assert warm_plan.candidate_count >= 2
    assert any(a.get("reason") for a in warm_plan.rejected_alternatives)


async def test_single_candidate_results_record_why(requires_postgres, session, test_principal):
    """Section 15: a single-candidate result is valid only where no alternative
    exists, and the Plan object must say so explicitly."""
    planned = await run_service.create_plan(
        session,
        principal=test_principal,
        intent="cheapest nonstop flights from Hyderabad to Da Nang in late November",
    )
    plan = planned["plan"]
    if plan.candidate_count == 1:
        assert plan.single_candidate_reason, (
            "a one-candidate plan must record why no alternative exists"
        )


async def test_planning_spends_nothing(requires_postgres, session, test_principal):
    """Planning calls an LLM, not SerpApi. That is what lets analysts plan."""
    planned = await run_service.create_plan(
        session,
        principal=test_principal,
        intent="recent reviews for a ramen shop in Seoul called Ichiran",
    )
    plan = planned["plan"]
    assert plan.naive_cost > 0
    # Locale inference is a routing discriminator (section 53).
    assert plan.parameter_bindings.get("gl") == "kr"
    assert plan.parameter_bindings.get("hl") == "ko"
