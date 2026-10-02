"""SerpFlow Python SDK (section 59).

    from serpflow import SerpFlow

    client = SerpFlow(api_key="sf_test_...")
    result = client.search("flights from Hyderabad to Da Nang in late November")
    print(result.plan.marginal_cost, "credits on the margin")

Three verbs mirror the service layer::

    route(intent)    plan only, no execution, no credits
    run(intent)      execute a plan
    search(intent)   plan with replanning, then execute

``SerpApiCompat`` is the drop-in: change only the base URL and existing SerpApi
code routes through SerpFlow, gaining caching and budget enforcement without
adopting routing at all.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

__all__ = [
    "AsyncSerpFlow",
    "PlanView",
    "RunEvent",
    "SearchResult",
    "SerpApiCompat",
    "SerpFlow",
    "SerpFlowError",
]

DEFAULT_BASE_URL = os.environ.get("SERPFLOW_BASE_URL", "http://localhost:8000")


class SerpFlowError(RuntimeError):
    """An error returned by the SerpFlow API, with its machine code intact."""

    def __init__(self, code: str, message: str, *, status: int = 0, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id

    def __str__(self) -> str:
        suffix = " (request " + self.request_id + ")" if self.request_id else ""
        return self.code + ": " + self.message + suffix


@dataclass(slots=True)
class PlanView:
    """The parts of a Plan a caller usually wants."""

    id: str
    intent: str
    engines: list[str]
    naive_cost: int
    marginal_cost: int
    savings: int
    candidate_count: int
    confidence: float
    catalog_version: str
    warm_steps: list[dict[str, Any]] = field(default_factory=list)
    marginal_replan_changed_selection: bool = False
    replan_explanation: str | None = None
    rejected_alternatives: list[dict[str, Any]] = field(default_factory=list)
    budget_reduction: dict[str, Any] | None = None
    projected_full_scale_cost: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PlanView:
        return cls(
            id=payload["id"],
            intent=payload["intent"],
            engines=[step["engine"] for step in payload.get("steps", [])],
            naive_cost=payload["naive_cost"],
            marginal_cost=payload["marginal_cost"],
            savings=payload.get("savings", 0),
            candidate_count=payload.get("candidate_count", 0),
            confidence=payload.get("confidence", 0.0),
            catalog_version=payload.get("catalog_version", ""),
            warm_steps=payload.get("warm_steps", []),
            marginal_replan_changed_selection=payload.get(
                "marginal_replan_changed_selection", False
            ),
            replan_explanation=payload.get("replan_explanation"),
            rejected_alternatives=payload.get("rejected_alternatives", []),
            budget_reduction=payload.get("budget_reduction"),
            projected_full_scale_cost=payload.get("projected_full_scale_cost"),
            raw=payload,
        )


@dataclass(slots=True)
class SearchResult:
    run_id: str
    status: str
    mode: str
    credits_spent: int
    credits_saved: int
    plan: PlanView
    results: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> list[dict[str, Any]]:
        return (self.results.get("summary") or {}).get("items", [])


@dataclass(slots=True)
class RunEvent:
    stage: str
    status: str
    elapsed_ms: float
    detail: dict[str, Any]
    type: str


def _unwrap(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        raise SerpFlowError(
            error.get("code", "HTTP_" + str(response.status_code)),
            error.get("message", response.text[:300]),
            status=response.status_code,
            request_id=error.get("request_id"),
        )
    if response.status_code == 204:
        return {}
    return response.json()


class SerpFlow:
    """Synchronous client."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        project_id: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("SERPFLOW_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "No API key. Pass api_key=, or set SERPFLOW_API_KEY. A test key "
                "routes to the deterministic mock and consumes zero SerpApi credits."
            )
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.project_id = project_id
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, headers=self._headers()
        )

    def _headers(self) -> dict[str, str]:
        headers = {"X-API-Key": self.api_key, "content-type": "application/json"}
        if self.project_id:
            headers["X-SerpFlow-Project"] = self.project_id
        return headers

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SerpFlow:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ---------------------------------------------------------------- verbs
    def route(self, intent: str, *, budget: int | None = None) -> PlanView:
        """Plan without executing. Calls a language model, not SerpApi, so it
        consumes zero credits."""
        payload = _unwrap(
            self._client.post(
                "/v1/plan",
                json={"intent": intent, "budget": budget, "project_id": self.project_id},
            )
        )
        return PlanView.from_payload(payload)

    plan = route

    def search(self, intent: str, *, budget: int | None = None) -> SearchResult:
        """Plan with cache-aware replanning, then execute."""
        payload = _unwrap(
            self._client.post(
                "/v1/search",
                json={"intent": intent, "budget": budget, "project_id": self.project_id},
            )
        )
        return SearchResult(
            run_id=payload["run"]["id"],
            status=payload["run"]["status"],
            mode=payload["mode"]["label"],
            credits_spent=payload["run"]["credits_spent"],
            credits_saved=payload["run"]["credits_saved"],
            plan=PlanView.from_payload(payload["plan"]),
            results=payload.get("results", {}),
            raw=payload,
        )

    run = search

    def stream(self, intent: str, *, budget: int | None = None) -> Iterator[RunEvent]:
        """Start a search and yield each real backend stage transition."""
        accepted = _unwrap(
            self._client.post(
                "/v1/search",
                json={
                    "intent": intent,
                    "budget": budget,
                    "project_id": self.project_id,
                    "stream": True,
                },
            )
        )
        with self._client.stream("GET", "/v1/runs/" + accepted["run_id"] + "/stream") as response:
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[5:].strip())
                if payload.get("type") == "heartbeat":
                    continue
                yield RunEvent(
                    stage=payload["stage"],
                    status=payload["status"],
                    elapsed_ms=payload["elapsed_ms"],
                    detail=payload.get("detail", {}),
                    type=payload.get("type", "stage"),
                )
                if payload.get("type") in ("complete", "error"):
                    return

    # ------------------------------------------------------------ inspect
    def get_run(self, run_id: str) -> dict[str, Any]:
        return _unwrap(self._client.get("/v1/runs/" + run_id))

    def explain(self, run_id: str) -> dict[str, Any]:
        """Which plans were considered, and why the selected one won."""
        run = self.get_run(run_id)
        plan = run.get("plan") or {}
        return {
            "run_id": run_id,
            "intent": run.get("intent"),
            "selected": [step["engine"] for step in plan.get("steps", [])],
            "naive_cost": plan.get("naive_cost"),
            "marginal_cost": plan.get("marginal_cost"),
            "changed_selection": plan.get("marginal_replan_changed_selection"),
            "explanation": plan.get("replan_explanation"),
            "candidates": plan.get("candidates", []),
            "rejected_alternatives": plan.get("rejected_alternatives", []),
        }

    def replay(self, run_id: str) -> SearchResult:
        payload = _unwrap(self._client.post("/v1/runs/" + run_id + "/replay"))
        return SearchResult(
            run_id=payload["run"]["id"],
            status=payload["run"]["status"],
            mode=payload["mode"]["label"],
            credits_spent=payload["run"]["credits_spent"],
            credits_saved=payload["run"]["credits_saved"],
            plan=PlanView.from_payload(payload["plan"]),
            results=payload.get("results", {}),
            raw=payload,
        )

    def runs(self, limit: int = 25, **filters: Any) -> list[dict[str, Any]]:
        params = {"limit": limit, **{k: v for k, v in filters.items() if v is not None}}
        return _unwrap(self._client.get("/v1/runs", params=params))["items"]

    def catalog(self, engine: str | None = None) -> dict[str, Any]:
        path = "/v1/catalog" + ("/engines/" + engine if engine else "")
        return _unwrap(self._client.get(path))

    def budgets(self) -> dict[str, Any]:
        return _unwrap(self._client.get("/v1/budgets"))

    def health(self) -> dict[str, Any]:
        return _unwrap(self._client.get("/readyz"))


class AsyncSerpFlow:
    """Asynchronous client with the same surface."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        project_id: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("SERPFLOW_API_KEY", "")
        if not self.api_key:
            raise ValueError("No API key. Pass api_key=, or set SERPFLOW_API_KEY.")
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.project_id = project_id
        headers = {"X-API-Key": self.api_key, "content-type": "application/json"}
        if project_id:
            headers["X-SerpFlow-Project"] = project_id
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout, headers=headers)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncSerpFlow:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def route(self, intent: str, *, budget: int | None = None) -> PlanView:
        response = await self._client.post(
            "/v1/plan",
            json={"intent": intent, "budget": budget, "project_id": self.project_id},
        )
        return PlanView.from_payload(_unwrap(response))

    plan = route

    async def search(self, intent: str, *, budget: int | None = None) -> SearchResult:
        response = await self._client.post(
            "/v1/search",
            json={"intent": intent, "budget": budget, "project_id": self.project_id},
        )
        payload = _unwrap(response)
        return SearchResult(
            run_id=payload["run"]["id"],
            status=payload["run"]["status"],
            mode=payload["mode"]["label"],
            credits_spent=payload["run"]["credits_spent"],
            credits_saved=payload["run"]["credits_saved"],
            plan=PlanView.from_payload(payload["plan"]),
            results=payload.get("results", {}),
            raw=payload,
        )

    run = search

    async def stream(self, intent: str, *, budget: int | None = None) -> AsyncIterator[RunEvent]:
        response = await self._client.post(
            "/v1/search",
            json={
                "intent": intent,
                "budget": budget,
                "project_id": self.project_id,
                "stream": True,
            },
        )
        accepted = _unwrap(response)
        async with self._client.stream(
            "GET", "/v1/runs/" + accepted["run_id"] + "/stream"
        ) as stream:
            async for line in stream.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[5:].strip())
                if payload.get("type") == "heartbeat":
                    continue
                yield RunEvent(
                    stage=payload["stage"],
                    status=payload["status"],
                    elapsed_ms=payload["elapsed_ms"],
                    detail=payload.get("detail", {}),
                    type=payload.get("type", "stage"),
                )
                if payload.get("type") in ("complete", "error"):
                    return


class SerpApiCompat:
    """SerpApi-compatible drop-in (section 59).

        from serpflow import SerpApiCompat

        search = SerpApiCompat({"engine": "google", "q": "coffee", "api_key": "sf_test_..."})
        results = search.get_dict()

    Existing SerpApi code keeps its shape. What changes is that the request now
    goes through SerpFlow's cache layers and budget enforcement, so a repeated
    query costs nothing and an exhausted budget fails with a clear code rather
    than a surprise invoice.

    This path does not re-route: you asked for an engine, you get that engine.
    Adopt ``SerpFlow.search`` when you want routing as well.
    """

    def __init__(self, params: dict[str, Any], *, base_url: str | None = None) -> None:
        self.params = dict(params)
        self.api_key = self.params.pop("api_key", None) or os.environ.get("SERPFLOW_API_KEY", "")
        self.engine = self.params.get("engine", "google")
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")

    def get_dict(self) -> dict[str, Any]:
        query = self.params.get("q") or self.params.get("query") or ""
        client = SerpFlow(self.api_key, base_url=self.base_url)
        try:
            result = client.search(str(query))
            payload = dict(result.results)
            payload["search_metadata"] = {
                "id": result.run_id,
                "status": "Success" if result.status == "succeeded" else "Error",
                "engine": self.engine,
                "serpflow_mode": result.mode,
                "serpflow_credits_spent": result.credits_spent,
                "serpflow_credits_saved": result.credits_saved,
            }
            payload["search_parameters"] = {"engine": self.engine, **self.params}
            return payload
        finally:
            client.close()

    def get_json(self) -> str:
        return json.dumps(self.get_dict(), default=str)
