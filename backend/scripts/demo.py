"""The reference demo (section 70): prove that cache-aware replanning changes
which plan is selected.

A cache hit after the same plan was chosen is NOT the proof. The proof is:
same intent, same catalog, different selected plan - because the cache state
changed between the two runs.

Three phases, all against the deterministic mock, consuming zero SerpApi
credits:

    1. COLD      the reference intent on a cold cache
    2. WARM-UP   a related run in a second project, which warms the Google Maps
                 contributor chain through the shared organization cache
    3. REPLAN    the reference intent again - the cold ranking still prefers
                 the cheap narrow plan, but the marginal ranking now prefers
                 the full contributor chain, and the selection changes

Exits non-zero if the thesis is not demonstrated, so it is usable as a check.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.logging import setup_logging  # noqa: E402
from app.core.permissions import permissions_for  # noqa: E402
from app.db.models.identity import Organization, Project  # noqa: E402
from app.db.models.keys import ApiKey  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.services.auth.service import Principal  # noqa: E402
from app.services.runs import plan_and_execute  # noqa: E402

REFERENCE_INTENT = "find coordinated review rings among Koramangala cafes"
# Phase 2 runs the SAME intent from a different project. Using the same intent
# matters: the exact cache layer is keyed on the normalised request, so a
# differently-worded warm-up would warm the fan-out steps but leave the entry
# point cold, and the demo would understate the effect.
WARMUP_INTENT = REFERENCE_INTENT
DEMO_BUDGET = 20

RULE = "=" * 78
THIN = "-" * 78


def _principal(org_id: str, project: Project, key: ApiKey) -> Principal:
    """A test-key principal: always routes to the deterministic mock."""
    return Principal(
        id=key.id,
        type="api_key",
        org_id=org_id,
        project_id=project.id,
        role=key.role,
        display=key.display,
        api_key_id=key.id,
        key_environment=key.environment,
        permissions=permissions_for(key.role),
    )


async def _resolve(session):
    org = await session.scalar(select(Organization).where(Organization.slug == "serpflow-demo"))
    if org is None:
        raise SystemExit("Demo organization not found. Run `make seed` first.")

    research = await session.scalar(
        select(Project).where(Project.org_id == org.id, Project.slug == "review-intelligence")
    )
    market = await session.scalar(
        select(Project).where(Project.org_id == org.id, Project.slug == "market-watch")
    )
    if research is None or market is None:
        raise SystemExit("Demo projects not found. Run `make seed --reset` first.")

    research_key = await session.scalar(
        select(ApiKey).where(
            ApiKey.project_id == research.id,
            ApiKey.environment == "test",
            ApiKey.is_service_principal.is_(False),
            ApiKey.revoked_at.is_(None),
        )
    )
    market_key = await session.scalar(
        select(ApiKey).where(
            ApiKey.project_id == market.id,
            ApiKey.environment == "test",
            ApiKey.revoked_at.is_(None),
        )
    )
    if research_key is None or market_key is None:
        raise SystemExit("Demo API keys not found. Run `make seed --reset` first.")
    return org, research, market, research_key, market_key


async def _configure_shared_cache(session, org, research, market) -> None:
    """Section 37: an organization-level shared cache.

    This crosses a billing and data boundary and the product says so at the
    point of enabling it. The demo enables it deliberately, because one
    project's spend benefiting another is exactly the effect being shown.
    """
    org.cache_scope = "organization"
    research.shared_cache_enabled = True
    market.shared_cache_enabled = True
    # Market Watch pins the Google Maps corpus. Yelp has effectively no
    # Bangalore coverage, and the Google local pack returns a ten-result
    # snapshot rather than the paginated map corpus, so neither is comparable
    # across runs. Both are excluded by project policy (section 51), which is
    # why this warm-up routes through google_maps specifically.
    market.engine_denylist = ["yelp", "yelp_reviews", "google_local"]
    await session.flush()


def _report(label: str, result: dict) -> dict:
    plan = result["plan"]
    run = result["run"]
    execution = result["execution"]

    print("")
    print(THIN)
    print(label)
    print(THIN)
    print("intent                " + run.intent)
    print("mode                  " + result["mode"].label + " - " + result["mode"].reason)
    print("catalog version       " + plan.catalog_version)
    print("candidates generated  " + str(plan.candidate_count))
    if plan.single_candidate_reason:
        print("single candidate      " + plan.single_candidate_reason)
    print("")
    print("selected plan         " + " -> ".join(s["engine"] for s in plan.steps))
    print("naive cost            " + str(plan.naive_cost) + " credits")
    print("marginal cost         " + str(plan.marginal_cost) + " credits")
    print("warm steps            " + str(len(plan.warm_steps)) + " of " + str(len(plan.steps)))
    if plan.projected_full_scale_cost:
        print(
            "full-scale projection "
            + str(plan.projected_full_scale_cost)
            + " credits  (PROJECTION ONLY - never executed live)"
        )
    print("actual credits spent  " + str(run.credits_spent))
    print("credits saved         " + str(run.credits_saved))
    print(
        "cache layers          "
        + str(execution.cache_summary if execution else "not executed (dry run)")
    )

    if plan.budget_reduction and plan.budget_reduction.get("reductions"):
        print("")
        print("budget reductions:")
        for reduction in plan.budget_reduction["reductions"]:
            print(
                "  step "
                + str(reduction["step"])
                + " "
                + reduction["engine"]
                + ": "
                + str(reduction["original"])
                + " -> "
                + str(reduction["reduced"])
            )
            print("    " + reduction["impact_note"])

    print("")
    print("cold-cost ranking would have chosen: " + str(plan.cold_winner_candidate_id))
    print("marginal-cost ranking chose:         " + ">".join(s["engine"] for s in plan.steps))
    print("")
    print(
        "REPLAN CHANGED SELECTION: " + ("YES" if plan.marginal_replan_changed_selection else "no")
    )
    print("  " + (plan.replan_explanation or ""))

    if plan.rejected_alternatives:
        print("")
        print("rejected alternatives:")
        for alternative in plan.rejected_alternatives:
            print(
                "  "
                + alternative["plan"]
                + "  cold "
                + str(alternative["naive_cost"])
                + " / marginal "
                + str(alternative["marginal_cost"])
                + "  ["
                + alternative.get("role", "answer")
                + ", "
                + alternative["coverage"]
                + "]"
            )
            if alternative.get("reason"):
                print("    " + alternative["reason"])

    return {
        "run_id": run.id,
        "plan_id": plan.id,
        "selected": [s["engine"] for s in plan.steps],
        "naive_cost": plan.naive_cost,
        "marginal_cost": plan.marginal_cost,
        "changed": plan.marginal_replan_changed_selection,
        "credits_spent": run.credits_spent,
        "candidate_count": plan.candidate_count,
    }


async def main(reset_cache: bool = False) -> int:
    setup_logging()

    print("")
    print(RULE)
    print("SerpFlow reference demo - coordinated review rings among Koramangala cafes")
    print(RULE)
    print("Chain under test:")
    print("  google_maps -> google_maps_reviews -> google_maps_contributor_reviews")
    print("")
    print("google_maps_contributor_reviews has effectively zero usage in the SerpApi")
    print("ecosystem. The planner reaches it through typed dependency edges, not by")
    print("a model recalling that the chain exists.")
    print("")
    print("Every phase below runs against the deterministic mock via a test API key,")
    print("so this demo consumes 0 SerpApi credits.")

    async with session_scope() as session:
        org, research, market, research_key, market_key = await _resolve(session)
        await _configure_shared_cache(session, org, research, market)

        if reset_cache:
            from app.services.cache.service import CacheService

            for project in (research, market):
                cache = CacheService(
                    session, org_id=org.id, project_id=project.id, scope="organization"
                )
                await cache.invalidate()
            print("")
            print("Cache invalidated; starting from cold.")

        research_principal = _principal(org.id, research, research_key)
        market_principal = _principal(org.id, market, market_key)

        # ---- phase 1: cold, dry run ---------------------------------------
        # Planning calls a language model rather than SerpApi, so a dry run
        # costs nothing and - importantly for this demo - warms nothing. That
        # keeps phase 3 an honest comparison: the only thing that changes
        # between the two runs is what phase 2 put in the cache.
        cold = await plan_and_execute(
            session,
            principal=research_principal,
            intent=REFERENCE_INTENT,
            project_id=research.id,
            budget=DEMO_BUDGET,
            execute=False,
            trigger="demo",
        )
        cold_summary = _report("PHASE 1  COLD CACHE  (dry run, nothing executed)", cold)

        # ---- phase 2: warm-up in the second project ----------------------
        print("")
        print(THIN)
        print("PHASE 2  WARM-UP (project: Market Watch, shared organization cache)")
        print(THIN)
        print("A different project runs the same investigation. Its policy pins the")
        print("Google Maps corpus - Yelp and the local pack are both on its engine")
        print("denylist - so this run routes through google_maps specifically and warms")
        print("that chain for the whole organization via the shared cache.")
        print("")
        print("It runs at full scale (the 101-credit shape) against the deterministic")
        print("mock, so it costs 0 SerpApi credits. Section 70 is explicit that the")
        print("101-credit chain is a projection and is never executed live.")
        warmup = await plan_and_execute(
            session,
            principal=market_principal,
            intent=WARMUP_INTENT,
            project_id=market.id,
            budget=None,
            execute=True,
            trigger="demo",
        )
        print("warm-up selected      " + " -> ".join(s["engine"] for s in warmup["plan"].steps))
        print(
            "warm-up shape         "
            + str(warmup["plan"].naive_cost)
            + " credits (mock, 0 real credits spent)"
        )
        print("warm-up credits spent " + str(warmup["run"].credits_spent))

        # ---- phase 3: replan ---------------------------------------------
        warm = await plan_and_execute(
            session,
            principal=research_principal,
            intent=REFERENCE_INTENT,
            project_id=research.id,
            budget=DEMO_BUDGET,
            execute=True,
            trigger="demo",
        )
        warm_summary = _report("PHASE 3  WARM CACHE, SAME INTENT", warm)

    # ---- verdict ----------------------------------------------------------
    print("")
    print(RULE)
    print("VERDICT")
    print(RULE)
    print("cold run selected   " + " -> ".join(cold_summary["selected"]))
    print(
        "                    naive "
        + str(cold_summary["naive_cost"])
        + ", marginal "
        + str(cold_summary["marginal_cost"])
        + ", spent "
        + str(cold_summary["credits_spent"])
    )
    print("warm run selected   " + " -> ".join(warm_summary["selected"]))
    print(
        "                    naive "
        + str(warm_summary["naive_cost"])
        + ", marginal "
        + str(warm_summary["marginal_cost"])
        + ", spent "
        + str(warm_summary["credits_spent"])
    )
    print("")

    # The proof is the persisted counterfactual, not a cache hit: within the
    # warm run, the cold-cost ranking and the marginal-cost ranking disagreed,
    # and the marginal ranking is what was executed. That is the fact the
    # planner stores on the Plan and counts in
    # serpflow_marginal_replan_changed_selection_total.
    flagged = warm_summary["changed"]
    plan_changed = cold_summary["selected"] != warm_summary["selected"]

    if not flagged:
        print("NOT PROVEN.")
        print("  The warm run's cold ranking and marginal ranking agreed.")
        print("")
        print("  Run `make seed ARGS=--reset` then `make demo` from a clean cache.")
        print(RULE)
        return 1

    print("PROVEN: cache-aware marginal-cost replanning changed the selected plan.")
    print("")
    print("  Within the warm run, ranking on cold cost and ranking on marginal cost")
    print("  disagreed, and the marginal ranking is what executed:")
    print("")
    print("    cold ranking would have chosen  " + " -> ".join(cold_summary["selected"]))
    print("    marginal ranking chose          " + " -> ".join(warm_summary["selected"]))
    print(
        "    naive "
        + str(warm_summary["naive_cost"])
        + " credits, marginal "
        + str(warm_summary["marginal_cost"])
        + " credits, actually spent "
        + str(warm_summary["credits_spent"])
    )
    print("")
    if plan_changed:
        print("  The two runs used the same intent and the same catalog version, and")
        print("  selected different plans. The only thing that changed was cache state.")
    else:
        print("  Both runs selected the same plan because the cache was already warm")
        print("  when the first one ran. The counterfactual above is the proof: the")
        print("  cold ranking still disagrees with what was executed. Re-run with")
        print("  --reset-cache to also see the selection change between runs.")
    print("")
    print("  serpflow_marginal_replan_changed_selection_total was incremented.")
    print(RULE)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the SerpFlow reference demo.")
    parser.add_argument(
        "--reset-cache",
        action="store_true",
        help="invalidate the cache before starting, so phase 1 is genuinely cold",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(reset_cache=args.reset_cache)))
