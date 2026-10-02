"""SerpApi HTTP client, plus the Searches Archive (section 19).

Archived retrievals consume no credit, so the executor checks the archive
before paying for a live call. ``get_archived`` and ``search`` are deliberately
separate methods so no code path can accidentally bill for a reread.

The credential is passed in at call time and never stored on the instance for
longer than the request. Only the executor ever constructs this client with a
real key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import UpstreamError, UpstreamQuotaExhaustedError
from app.core.logging import get_logger

log = get_logger("serpflow.serpapi")

NON_SEMANTIC_PARAMS = {"api_key", "output", "no_cache", "async", "zero_trace", "json_restrictor"}


@dataclass(slots=True)
class SerpApiResponse:
    payload: dict[str, Any]
    http_status: int
    latency_ms: float
    search_id: str | None = None
    credited: bool = True
    source: str = "live"
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.http_status >= 400 or bool(self.payload.get("error"))

    @property
    def error_message(self) -> str | None:
        err = self.payload.get("error")
        return str(err) if err else None


class SerpApiClient:
    """Thin async client. No retries on 4xx - a bad request is not transient."""

    def __init__(self, api_key: str, *, base_url: str | None = None, timeout: float | None = None):
        self._api_key = api_key
        self.base_url = (base_url or settings.serpapi_base_url).rstrip("/")
        self.timeout = timeout or settings.serpapi_timeout_seconds

    @staticmethod
    def strip_non_semantic(params: dict[str, Any]) -> dict[str, Any]:
        """Remove parameters that do not change the result (section 17)."""
        return {k: v for k, v in params.items() if k not in NON_SEMANTIC_PARAMS and v is not None}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.4, min=0.4, max=3),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.get(self.base_url + path, params=params)

    async def search(self, engine: str, params: dict[str, Any]) -> SerpApiResponse:
        """One billable upstream search."""
        started = time.perf_counter()
        request = self.strip_non_semantic(params)
        request["engine"] = engine
        request["api_key"] = self._api_key
        request["output"] = "json"

        try:
            response = await self._get("/search", request)
        except httpx.HTTPError as exc:
            raise UpstreamError(
                "SerpApi request failed: " + type(exc).__name__,
                details={"engine": engine},
            ) from exc

        latency = (time.perf_counter() - started) * 1000.0
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": "upstream returned a non-JSON body"}

        if response.status_code == 401:
            raise UpstreamError(
                "SerpApi rejected the credential.",
                code="CREDENTIAL_REJECTED",
                status_code=502,
                details={"engine": engine},
            )
        if response.status_code == 429 or _is_quota_error(payload):
            # Distinct from BUDGET_EXHAUSTED (section 39): this is the upstream
            # account running dry, and the fix is upstream capacity.
            raise UpstreamQuotaExhaustedError(details={"engine": engine})

        return SerpApiResponse(
            payload=payload,
            http_status=response.status_code,
            latency_ms=latency,
            search_id=(payload.get("search_metadata") or {}).get("id"),
            credited=True,
            source="live",
            headers={k.lower(): v for k, v in response.headers.items()},
        )

    async def get_archived(self, search_id: str) -> SerpApiResponse:
        """Re-read an archived search. Consumes no credit (section 19)."""
        started = time.perf_counter()
        try:
            response = await self._get(
                "/searches/" + search_id + ".json", {"api_key": self._api_key}
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(
                "SerpApi archive read failed: " + type(exc).__name__,
                details={"search_id": search_id},
            ) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {"error": "archive returned a non-JSON body"}

        return SerpApiResponse(
            payload=payload,
            http_status=response.status_code,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            search_id=search_id,
            credited=False,
            source="archive",
        )

    async def list_archive(
        self, *, engine: str | None = None, num: int = 50
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"api_key": self._api_key, "num": num}
        if engine:
            params["engine"] = engine
        try:
            response = await self._get("/searches", params)
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        if isinstance(body, list):
            return body
        return body.get("searches") or []

    async def account(self) -> dict[str, Any]:
        """Account endpoint, polled for quota reconciliation (section 40)."""
        try:
            response = await self._get("/account", {"api_key": self._api_key})
            if response.status_code >= 400:
                raise UpstreamError(
                    "SerpApi account endpoint returned HTTP " + str(response.status_code)
                )
            return response.json()
        except httpx.HTTPError as exc:
            raise UpstreamError("SerpApi account check failed: " + type(exc).__name__) from exc

    async def validate(self) -> dict[str, Any]:
        """One cheap upstream call to prove a credential works (section 26)."""
        account = await self.account()
        return {
            "valid": True,
            "plan_name": account.get("plan_name"),
            "searches_left": account.get("total_searches_left")
            or account.get("plan_searches_left"),
            "this_month_usage": account.get("this_month_usage"),
            "account_id": account.get("account_id"),
        }


def _is_quota_error(payload: dict[str, Any]) -> bool:
    error = str(payload.get("error") or "").lower()
    return any(
        marker in error
        for marker in ("run out of searches", "exceeded", "no searches left", "quota")
    )


__all__ = ["NON_SEMANTIC_PARAMS", "SerpApiClient", "SerpApiResponse"]
