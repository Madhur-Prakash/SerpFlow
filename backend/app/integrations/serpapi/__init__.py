"""SerpApi gateway with explicit mode precedence (section 21).

    1. A `test` API key ALWAYS routes to the deterministic mock, regardless of
       SERPFLOW_MODE. This is absolute and cannot be overridden.

    2. For `live` API keys, SERPFLOW_MODE decides:
         live    -> normal execution against SerpApi
         record  -> execute live AND persist cassettes
         replay  -> serve from cassettes only; fail loudly on miss

The resolved mode travels with every response and is stamped on the run, the
step and the ``X-SerpFlow-Mode`` header. Replayed or mocked data is never
presented as live.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.exceptions import NoUpstreamCredentialError
from app.core.logging import get_logger
from app.integrations.serpapi.cassettes import CassetteStore, cassette_key
from app.integrations.serpapi.client import SerpApiClient, SerpApiResponse
from app.integrations.serpapi.mock import generate as mock_generate
from app.integrations.serpapi.mock import mock_account

log = get_logger("serpflow.serpapi.gateway")

MODE_LIVE = "live"
MODE_RECORD = "record"
MODE_REPLAY = "replay"
MODE_MOCK = "mock"


@dataclass(frozen=True, slots=True)
class ResolvedMode:
    """What will actually happen, and why. Surfaced in the UI verbatim."""

    mode: str
    reason: str
    credited: bool

    @property
    def label(self) -> str:
        return self.mode.upper()

    @property
    def needs_credential(self) -> bool:
        """Only live and record actually reach SerpApi, so only they require a
        decrypted upstream credential."""
        return self.mode in (MODE_LIVE, MODE_RECORD)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "label": self.label,
            "reason": self.reason,
            "credited": self.credited,
        }


def resolve_mode(*, key_environment: str, configured_mode: str | None = None) -> ResolvedMode:
    """Mode precedence. Rule 1 is absolute and checked first."""
    if key_environment == "test":
        return ResolvedMode(
            mode=MODE_MOCK,
            reason=(
                "A test API key always routes to the deterministic mock and consumes "
                "zero SerpApi credits. This cannot be overridden by SERPFLOW_MODE."
            ),
            credited=False,
        )
    configured = (configured_mode or settings.serpflow_mode).lower()
    if configured == MODE_REPLAY:
        return ResolvedMode(
            mode=MODE_REPLAY,
            reason="SERPFLOW_MODE=replay: served from recorded cassettes, never the network.",
            credited=False,
        )
    if configured == MODE_RECORD:
        return ResolvedMode(
            mode=MODE_RECORD,
            reason="SERPFLOW_MODE=record: executes live against SerpApi and persists cassettes.",
            credited=True,
        )
    return ResolvedMode(
        mode=MODE_LIVE,
        reason="SERPFLOW_MODE=live: normal billable execution against SerpApi.",
        credited=True,
    )


class SerpApiGateway:
    """The single place an upstream search is issued from.

    ``api_key`` is only ever non-None when the caller is the executor, which is
    the only component permitted to decrypt a credential (section 25).
    """

    def __init__(
        self,
        *,
        mode: ResolvedMode,
        api_key: str | None = None,
        cassette_root: str | None = None,
    ) -> None:
        self.mode = mode
        self._api_key = api_key
        self.cassettes = CassetteStore(cassette_root)

    @property
    def needs_credential(self) -> bool:
        return self.mode.mode in (MODE_LIVE, MODE_RECORD)

    def _client(self) -> SerpApiClient:
        if not self._api_key:
            raise NoUpstreamCredentialError()
        return SerpApiClient(self._api_key)

    async def search(self, engine: str, params: dict[str, Any]) -> SerpApiResponse:
        clean = SerpApiClient.strip_non_semantic(params)

        if self.mode.mode == MODE_MOCK:
            started = time.perf_counter()
            payload = mock_generate(engine, clean)
            return SerpApiResponse(
                payload=payload,
                http_status=200,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                search_id=(payload.get("search_metadata") or {}).get("id"),
                credited=False,
                source=MODE_MOCK,
            )

        if self.mode.mode == MODE_REPLAY:
            started = time.perf_counter()
            # Raises ReplayMissError naming the missing file. No network here.
            payload = self.cassettes.load(engine, clean)
            return SerpApiResponse(
                payload=payload,
                http_status=200,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                search_id=(payload.get("search_metadata") or {}).get("id"),
                credited=False,
                source=MODE_REPLAY,
            )

        response = await self._client().search(engine, clean)
        if self.mode.mode == MODE_RECORD and not response.is_error:
            self.cassettes.save(
                engine,
                clean,
                response.payload,
                http_status=response.http_status,
                latency_ms=response.latency_ms,
            )
        return response

    async def get_archived(self, search_id: str) -> SerpApiResponse:
        """Archive reads are free in every mode."""
        if self.mode.mode in (MODE_MOCK, MODE_REPLAY):
            raise NotImplementedError(
                "Archive reads are not meaningful in " + self.mode.mode + " mode."
            )
        return await self._client().get_archived(search_id)

    async def account(self) -> dict[str, Any]:
        if self.mode.mode == MODE_MOCK:
            return mock_account()
        return await self._client().account()

    async def validate(self) -> dict[str, Any]:
        if self.mode.mode == MODE_MOCK:
            return {"valid": True, "plan_name": "mock", "searches_left": 250, "mock": True}
        return await self._client().validate()


__all__ = [
    "MODE_LIVE",
    "MODE_MOCK",
    "MODE_RECORD",
    "MODE_REPLAY",
    "CassetteStore",
    "ResolvedMode",
    "SerpApiClient",
    "SerpApiGateway",
    "SerpApiResponse",
    "cassette_key",
    "mock_generate",
    "resolve_mode",
]
