"""Groq-backed LLM adapter.

Groq serves the OpenAI-compatible chat completions API, so this is a thin
httpx client with strict JSON-mode decoding - no vendor SDK and no hidden
retries.

Two deliberate constraints:

* The model only ever sees the retrieved shortlist, never all 54 engine
  schemas (section 13 stage A).
* The model never invents a chain or a freshness level in isolation. Stage D
  computes chains from the typed graph, and every model-proposed engine name,
  parameter key and freshness level is validated against the catalog and the
  deterministic rules before it is accepted. A hallucinated engine is dropped
  and recorded, not executed.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.core.routes import resolve_route
from app.core.text import (
    classify_query,
    extract_entities,
    extract_location_phrase,
    infer_freshness,
    infer_locale,
    normalize_dates,
)
from app.integrations.llm.base import (
    FRESHNESS_ORDER,
    EngineChoice,
    SelectionResult,
    SynthesisResult,
)
from app.integrations.llm.mock import MockLLMAdapter

log = get_logger("serpflow.llm.groq")

SELECT_SYSTEM = """You route natural-language search intents to SerpApi engines.

You are given an intent and a shortlist of candidate engines with their
capability tags, required parameters and documented trade-offs. Choose the
engines that actually answer the intent.

Rules:
- Only choose engines from the supplied candidate list. Never name an engine
  that is not in the list.
- Do not design multi-step chains. A graph algorithm computes valid chains
  from typed dependency edges; your job is to pick the target capability.
- For every candidate you do not choose, give a concrete reason referencing its
  coverage or trade-off, not a generic statement.
- Confidence is a calibrated probability between 0 and 1. Use values below 0.6
  when the intent is genuinely ambiguous.

Respond with JSON only, matching exactly:
{"chosen":[{"engine":"...","confidence":0.0,"reason":"..."}],
 "rejected":[{"engine":"...","reason":"..."}],
 "reasoning":"one or two sentences"}"""

SYNTH_SYSTEM = """You bind parameters for a SerpApi search.

Given an intent and the chosen engines' parameter schemas, produce the concrete
parameter values. Normalise dates to ISO YYYY-MM-DD. Infer locale from place
names (Seoul implies gl=kr and hl=ko). Classify how fresh the result must be.

freshness is exactly one of:
  realtime  (under 15 minutes: live prices, fares, breaking news)
  fresh     (under 24 hours: today, latest, current, hotel and job listings)
  recent    (under 7 days: recent reviews, local listings)
  stable    (any valid TTL: patents, papers, reference lookups)

Respond with JSON only, matching exactly:
{"parameters":{"q":"...","gl":"..","hl":".."},
 "freshness":"recent",
 "freshness_signals":["..."],
 "entities":["..."],
 "query_class":"...",
 "notes":"..."}"""


class GroqUnavailable(RuntimeError):
    pass


class GroqLLMAdapter:
    """Real adapter. Falls back to the deterministic adapter when unconfigured,
    and says so in the result rather than pretending the model ran."""

    name = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key: str = api_key or settings.groq_api_key or ""
        self.model = model or settings.groq_model
        self.base_url = settings.groq_base_url.rstrip("/")
        self._fallback = MockLLMAdapter()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    # ----------------------------------------------------------------- http
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def _complete(self, system: str, user: str, *, max_tokens: int = 1200) -> dict[str, Any]:
        if not self.configured:
            raise GroqUnavailable("GROQ_API_KEY is not set")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
            response = await client.post(
                self.base_url + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer " + self.api_key},
            )
        if response.status_code >= 400:
            raise GroqUnavailable("groq returned HTTP " + str(response.status_code))
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise GroqUnavailable("groq returned non-JSON content") from exc

    # ------------------------------------------------------------- stage B
    async def select_engines(
        self,
        intent: str,
        candidates: list[dict[str, Any]],
        *,
        max_select: int = 3,
    ) -> SelectionResult:
        started = time.perf_counter()
        allowed = {c["engine"] for c in candidates}

        if not self.configured:
            result = await self._fallback.select_engines(intent, candidates, max_select=max_select)
            result.provider = "mock"
            result.model = "deterministic-v1 (GROQ_API_KEY unset)"
            return result

        user = json.dumps(
            {
                "intent": intent,
                "max_select": max_select,
                "candidates": [
                    {
                        "engine": c["engine"],
                        "purpose": c.get("purpose", ""),
                        "capability_tags": c.get("capability_tags", []),
                        "requires": list(c.get("requires", {}) or {}),
                        "substitutes": c.get("substitutes", []),
                        "cost": c.get("cost", 1),
                        "latency_class": c.get("latency_class", "medium"),
                    }
                    for c in candidates
                ],
            },
            ensure_ascii=False,
        )

        try:
            raw = await self._complete(SELECT_SYSTEM, user)
        except Exception as exc:
            log.warning(
                "groq selection failed, using deterministic selector",
                extra={"event": "llm.fallback", "error": type(exc).__name__},
            )
            result = await self._fallback.select_engines(intent, candidates, max_select=max_select)
            result.provider = "mock"
            result.model = "deterministic-v1 (groq unavailable)"
            return result

        chosen: list[EngineChoice] = []
        rejected: list[dict[str, Any]] = list(raw.get("rejected") or [])
        for item in raw.get("chosen") or []:
            engine = str(item.get("engine", "")).strip()
            if engine not in allowed:
                # A hallucinated engine is recorded, not executed.
                rejected.append(
                    {
                        "engine": engine or "(unnamed)",
                        "reason": "model proposed an engine outside the retrieved candidate set",
                        "hallucinated": True,
                    }
                )
                continue
            try:
                confidence = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            chosen.append(
                EngineChoice(
                    engine=engine,
                    confidence=max(0.0, min(1.0, confidence)),
                    reason=str(item.get("reason", ""))[:400],
                )
            )

        if not chosen:
            fallback = await self._fallback.select_engines(
                intent, candidates, max_select=max_select
            )
            chosen = fallback.chosen
            rejected.extend(fallback.rejected)

        return SelectionResult(
            chosen=chosen[:max_select],
            rejected=rejected,
            reasoning=str(raw.get("reasoning", ""))[:600],
            provider=self.name,
            model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------- stage C
    async def synthesize(self, intent: str, engine_specs: list[dict[str, Any]]) -> SynthesisResult:
        started = time.perf_counter()
        # The deterministic result is both the fallback and the validator.
        baseline = await self._fallback.synthesize(intent, engine_specs)

        if not self.configured:
            baseline.model = "deterministic-v1 (GROQ_API_KEY unset)"
            return baseline

        user = json.dumps(
            {
                "intent": intent,
                "today": time.strftime("%Y-%m-%d"),
                "engines": [
                    {
                        "engine": s.get("engine"),
                        "requires": s.get("requires", {}),
                        "optional": s.get("optional", []),
                        "locale_sensitive": s.get("locale_sensitive", []),
                        "volatility_prior": s.get("volatility_prior", "7d"),
                    }
                    for s in engine_specs
                ],
            },
            ensure_ascii=False,
        )

        try:
            raw = await self._complete(SYNTH_SYSTEM, user, max_tokens=900)
        except Exception as exc:
            log.warning(
                "groq synthesis failed, using deterministic synthesis",
                extra={"event": "llm.fallback", "error": type(exc).__name__},
            )
            baseline.model = "deterministic-v1 (groq unavailable)"
            return baseline

        parameters = dict(baseline.parameters)
        model_params = raw.get("parameters")
        if isinstance(model_params, dict):
            allowed_keys = {
                "q",
                "query",
                "location",
                "gl",
                "hl",
                "text",
                "term",
                "find_desc",
                "find_loc",
                "search_query",
                "p",
                "k",
                "_nkw",
                "mauthors",
                "departure_id",
                "arrival_id",
                "outbound_date",
                "return_date",
                "check_in_date",
                "check_out_date",
                "geo",
                "date",
                "currency",
            }
            for key, value in model_params.items():
                if key in allowed_keys and isinstance(value, (str, int, float)):
                    parameters[key] = value

        # Locale and dates stay deterministic: a model that disagrees about
        # gl silently changes the result set, and that is a benchmark
        # discriminator we refuse to gamble on.
        locale, matched = infer_locale(intent)
        parameters["gl"] = locale.gl
        parameters["hl"] = locale.hl
        parameters.update(normalize_dates(intent))
        route = resolve_route(intent)
        parameters.update(route)
        if route and "date" in parameters:
            parameters.setdefault("outbound_date", parameters["date"])
        location = extract_location_phrase(intent)
        if location and "location" not in parameters:
            parameters["location"] = location

        freshness = str(raw.get("freshness", "")).strip().lower()
        prior = engine_specs[0].get("volatility_prior", "7d") if engine_specs else "7d"
        rule_level, rule_signals = infer_freshness(intent, volatility_prior=prior)
        signals = list(rule_signals)
        if freshness in FRESHNESS_ORDER:
            # Accept the model only when it is stricter than the rules; it may
            # tighten the bar, never loosen it.
            if FRESHNESS_ORDER.index(freshness) < FRESHNESS_ORDER.index(rule_level):
                signals.append("model tightened to " + freshness)
                rule_level = freshness
            elif freshness != rule_level:
                signals.append(
                    "model proposed " + freshness + "; deterministic rules kept " + rule_level
                )
        model_signals = raw.get("freshness_signals")
        if isinstance(model_signals, list):
            signals.extend(str(s)[:120] for s in model_signals[:3])

        entities = sorted(extract_entities(intent))
        model_entities = raw.get("entities")
        if isinstance(model_entities, list):
            entities = sorted(set(entities) | {str(e).lower()[:60] for e in model_entities[:12]})

        return SynthesisResult(
            parameters=parameters,
            locale={"gl": locale.gl, "hl": locale.hl, "matched": matched or ""},
            freshness=rule_level,
            freshness_signals=signals,
            entities=entities,
            query_class=str(raw.get("query_class") or classify_query(intent)),
            notes=str(raw.get("notes", ""))[:400],
            provider=self.name,
            model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    async def health(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "provider": self.name,
                "model": self.model,
                "status": "unconfigured",
                "detail": "GROQ_API_KEY is not set; the deterministic adapter is in use.",
            }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.base_url + "/models",
                    headers={"Authorization": "Bearer " + self.api_key},
                )
            return {
                "provider": self.name,
                "model": self.model,
                "status": "ok" if response.status_code < 400 else "error",
                "http_status": response.status_code,
            }
        except Exception as exc:
            return {
                "provider": self.name,
                "model": self.model,
                "status": "error",
                "detail": type(exc).__name__,
            }


__all__ = ["GroqLLMAdapter", "GroqUnavailable"]
