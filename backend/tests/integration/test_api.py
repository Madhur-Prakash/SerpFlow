"""Integration tests against the real FastAPI app, PostgreSQL and Redis."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from httpx import ASGITransport

from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def client(requires_postgres):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://serpflow.test", timeout=60.0
    ) as http:
        yield http


@pytest.fixture
async def account(client):
    """Register an account through the public API and return its handles."""
    suffix = uuid.uuid4().hex[:8]
    email = "it-" + suffix + "@serpflow-tests.dev"
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "integration-password-1",
            "full_name": "Integration User",
            "organization_name": "Integration Org " + suffix,
        },
    )
    assert response.status_code == 201, response.text
    tokens = response.json()
    auth = {"Authorization": "Bearer " + tokens["access_token"]}

    projects = (await client.get("/v1/projects", headers=auth)).json()
    project_id = projects[0]["id"]

    created = await client.post(
        "/v1/projects/" + project_id + "/keys",
        headers=auth,
        json={"name": "it key", "environment": "test", "role": "developer"},
    )
    assert created.status_code == 201, created.text
    return {
        "email": email,
        "tokens": tokens,
        "auth": auth,
        "project_id": project_id,
        "api_key": created.json()["plaintext"],
        "key_id": created.json()["key"]["id"],
    }


# --------------------------------------------------------------------------
# infrastructure
# --------------------------------------------------------------------------
async def test_health_and_readiness(client):
    assert (await client.get("/healthz")).status_code == 200
    ready = await client.get("/readyz")
    assert ready.status_code in (200, 503)
    assert set(ready.json()["checks"]) >= {"postgres", "redis", "catalog", "object_storage"}


async def test_metrics_exposes_the_thesis_counter(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "serpflow_marginal_replan_changed_selection_total" in response.text
    assert "serpflow_semantic_guard_rejections_total" in response.text
    assert "serpflow_semantic_false_hit_reports_total" in response.text


async def test_openapi_is_served(client):
    spec = (await client.get("/openapi.json")).json()
    assert "/v1/search" in spec["paths"]
    assert "/v1/runs/{run_id}/stream" in spec["paths"]


# --------------------------------------------------------------------------
# authentication and authorization
# --------------------------------------------------------------------------
async def test_unauthenticated_requests_are_rejected(client):
    response = await client.post("/v1/plan", json={"intent": "cafes in Koramangala"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_malformed_api_key_is_rejected(client):
    response = await client.post(
        "/v1/plan",
        json={"intent": "cafes in Koramangala"},
        headers={"X-API-Key": "sf_live_nope_short"},
    )
    assert response.status_code == 401


async def test_refresh_rotation_invalidates_the_old_token(client, account):
    first = await client.post(
        "/v1/auth/refresh", json={"refresh_token": account["tokens"]["refresh_token"]}
    )
    assert first.status_code == 200
    replay = await client.post(
        "/v1/auth/refresh", json={"refresh_token": account["tokens"]["refresh_token"]}
    )
    assert replay.status_code == 401


async def test_revoked_key_stops_working_immediately(client, account):
    headers = {"X-API-Key": account["api_key"]}
    assert (await client.get("/v1/catalog/tags", headers=headers)).status_code == 200

    revoked = await client.delete(
        "/v1/keys/" + account["key_id"], headers=account["auth"], params={"reason": "test"}
    )
    assert revoked.status_code == 200
    # Section 33: the 60-second principal cache is invalidated on revoke, so
    # this must fail now rather than in a minute.
    assert (await client.get("/v1/catalog/tags", headers=headers)).status_code == 401


# --------------------------------------------------------------------------
# credentials (section 25)
# --------------------------------------------------------------------------
async def test_credential_responses_never_contain_the_secret(client, account):
    secret = "f" * 64
    created = await client.post(
        "/v1/credentials",
        headers=account["auth"],
        json={"name": "test credential", "api_key": secret, "validate_now": False},
    )
    assert created.status_code == 201, created.text
    body = created.text
    assert secret not in body
    assert "ciphertext" not in body
    assert "encrypted_dek" not in body

    payload = created.json()
    assert payload["fingerprint"]
    assert len(payload["fingerprint"]) == 8

    listed = await client.get("/v1/credentials", headers=account["auth"])
    assert secret not in listed.text


# --------------------------------------------------------------------------
# planning and execution
# --------------------------------------------------------------------------
async def test_plan_returns_candidates_and_the_counterfactual(client, account):
    response = await client.post(
        "/v1/plan",
        headers={"X-API-Key": account["api_key"]},
        json={"intent": "find coordinated review rings among Koramangala cafes", "budget": 20},
    )
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["candidate_count"] >= 2
    assert plan["steps"]
    assert plan["naive_cost"] >= plan["marginal_cost"]
    assert plan["catalog_version"]
    assert plan["rejected_alternatives"]
    assert all(step["freshness_requirement"] for step in plan["steps"])


async def test_search_executes_and_reports_provenance(client, account):
    response = await client.post(
        "/v1/search",
        headers={"X-API-Key": account["api_key"]},
        json={"intent": "recent reviews for cafes in Koramangala", "budget": 20},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["run"]["status"] == "succeeded"
    # A test key routes to the mock whatever SERPFLOW_MODE says.
    assert body["mode"]["label"] == "MOCK"
    assert body["mode"]["credited"] is False
    assert body["run"]["credits_spent"] == 0

    # Section 45 provenance headers.
    assert response.headers["X-SerpFlow-Run-Id"] == body["run"]["id"]
    assert response.headers["X-SerpFlow-Mode"]
    assert response.headers["X-SerpFlow-Cache"]
    assert response.headers["X-Request-Id"]


async def test_run_inspector_payload_is_complete(client, account):
    headers = {"X-API-Key": account["api_key"]}
    run_id = (
        await client.post(
            "/v1/search",
            headers=headers,
            json={"intent": "cafes in Koramangala with outdoor seating", "budget": 20},
        )
    ).json()["run"]["id"]

    detail = await client.get("/v1/runs/" + run_id, headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["steps"]
    assert body["plan"]["candidates"]
    assert body["provenance"]["mode"]
    for step in body["steps"]:
        assert step["cache_layer"]
        assert step["freshness_requirement"]


async def test_sse_stream_replays_real_stage_events(client, account):
    """Section 42: the UI animation is driven by real backend stage
    transitions, so the stream has to contain them."""
    headers = {"X-API-Key": account["api_key"]}
    run_id = (
        await client.post(
            "/v1/search",
            headers=headers,
            json={"intent": "bakeries in Koramangala", "budget": 20},
        )
    ).json()["run"]["id"]

    stages: list[str] = []
    async with client.stream("GET", "/v1/runs/" + run_id + "/stream", headers=headers) as stream:
        assert stream.status_code == 200
        async for line in stream.aiter_lines():
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:].strip())
            stages.append(event["stage"])
            assert "status" in event
            assert "elapsed_ms" in event
            assert "detail" in event
            if event.get("type") in ("complete", "error"):
                break

    for required in (
        "analyzing_intent",
        "finding_candidates",
        "synthesizing_parameters",
        "inferring_freshness",
        "finding_paths",
        "generating_candidates",
        "inspecting_cache",
        "calculating_marginal_cost",
        "reranking_plans",
        "checking_budget",
        "executing",
    ):
        assert required in stages, required


async def test_replay_creates_a_linked_run(client, account):
    headers = {"X-API-Key": account["api_key"]}
    original = (
        await client.post(
            "/v1/search",
            headers=headers,
            json={"intent": "coffee roasters in Koramangala", "budget": 20},
        )
    ).json()["run"]["id"]

    replayed = await client.post("/v1/runs/" + original + "/replay", headers=headers)
    assert replayed.status_code == 200
    assert replayed.json()["run"]["replay_of_run_id"] == original


async def test_false_hit_report_is_recorded(client, account):
    headers = {"X-API-Key": account["api_key"]}
    run_id = (
        await client.post(
            "/v1/search",
            headers=headers,
            json={"intent": "dessert places in Koramangala", "budget": 20},
        )
    ).json()["run"]["id"]

    reported = await client.post(
        "/v1/runs/" + run_id + "/report-false-hit",
        headers=headers,
        json={"note": "wrong neighbourhood", "invalidate_entry": True},
    )
    assert reported.status_code == 200

    metrics = (await client.get("/metrics")).text
    assert "serpflow_semantic_false_hit_reports_total" in metrics


# --------------------------------------------------------------------------
# catalog, cache, budgets, audit
# --------------------------------------------------------------------------
async def test_catalog_separates_dependency_and_substitute_edges(client, account):
    graph = await client.get("/v1/catalog/graph", headers=account["auth"])
    assert graph.status_code == 200
    body = graph.json()
    assert body["dependency_edges"]
    assert body["substitute_edges"]
    assert all(e["kind"] == "dependency" for e in body["dependency_edges"])
    assert all(e["kind"] == "substitute" for e in body["substitute_edges"])


async def test_catalog_paths_endpoint_finds_the_contributor_chain(client, account):
    response = await client.get(
        "/v1/catalog/engines/google_maps_contributor_reviews/paths",
        headers=account["auth"],
        params={"params": "q,location"},
    )
    assert response.status_code == 200
    assert response.json()["path_count"] >= 1


async def test_budget_exhaustion_is_distinct_from_upstream_quota(client, account):
    """Section 39: these are different events with different fixes."""
    budgets = (await client.get("/v1/budgets", headers=account["auth"])).json()
    project_budget = next(b for b in budgets["budgets"] if b["scope"] == "project")

    patched = await client.patch(
        "/v1/budgets/" + project_budget["id"],
        headers=account["auth"],
        json={"limit_credits": 1},
    )
    assert patched.status_code == 200
    assert patched.json()["limit_credits"] == 1

    from app.core.exceptions import BudgetExhaustedError, UpstreamQuotaExhaustedError

    assert BudgetExhaustedError().code == "BUDGET_EXHAUSTED"
    assert UpstreamQuotaExhaustedError().code == "UPSTREAM_QUOTA_EXHAUSTED"
    assert BudgetExhaustedError().message != UpstreamQuotaExhaustedError().message


async def test_audit_chain_verifies(client, account):
    verify = await client.get("/v1/audit/verify", headers=account["auth"])
    assert verify.status_code == 200
    body = verify.json()
    assert body["valid"] is True
    assert body["entries_checked"] >= 1


async def test_cache_dashboard_reports_layers(client, account):
    headers = {"X-API-Key": account["api_key"]}
    await client.post(
        "/v1/search",
        headers=headers,
        json={"intent": "tea rooms in Koramangala", "budget": 20},
    )
    dashboard = await client.get("/v1/cache", headers=account["auth"])
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert set(body["layers"]) >= {"exact", "semantic", "archive", "live"}
    assert "guard_rejections" in body


async def test_analytics_savings_decomposition(client, account):
    response = await client.get("/v1/analytics/savings", headers=account["auth"])
    assert response.status_code == 200
    labels = [step["label"] for step in response.json()["waterfall"]]
    assert labels == [
        "Naive execution",
        "Routing savings",
        "Exact cache savings",
        "Semantic cache savings",
        "Archive savings",
        "Actual spend",
    ]


async def test_errors_use_the_canonical_envelope_without_stack_traces(client, account):
    response = await client.get("/v1/runs/run_does_not_exist", headers=account["auth"])
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert "Traceback" not in response.text
    assert error["request_id"]
