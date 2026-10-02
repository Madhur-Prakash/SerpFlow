"""Benchmark harness (section 53).

Three systems, same 120 hand-authored tasks:

    unaided_llm      a frontier model writing SerpApi calls with no catalog
    embedding_only   retrieval with no selector and no path-finding
    serpflow         the full pipeline

The benchmark makes real LLM calls, so it runs on demand via ``make benchmark``
and is deliberately NOT part of CI. Results are committed per
``catalog_version``.

Accuracy is reported honestly, with an error analysis of failure modes. An
honest 78% with failure analysis is more credible than an unqualified claim.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.logging import get_logger
from app.db.models.benchmark import BenchmarkRun, BenchmarkTask, RoutingEval
from app.integrations.llm import LLMAdapter, get_llm
from app.integrations.llm.embedding import cosine_similarity, embed
from app.services.catalog.loader import CatalogIndex, load_catalog
from app.services.planner import candidates as stage_d
from app.services.planner import retrieval as stage_a
from app.services.planner.candidates import ROLE_ANSWER
from app.services.planner.cost import COVERAGE_RANK

log = get_logger("serpflow.benchmark")

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "benchmark"

SYSTEM_SERPFLOW = "serpflow"
SYSTEM_UNAIDED = "unaided_llm"
SYSTEM_EMBEDDING = "embedding_only"

FAILURE_MODES = (
    "wrong_engine",
    "missing_hop",
    "extra_hop",
    "locale_miss",
    "freshness_miss",
    "no_plan",
)


@dataclass(slots=True)
class TaskSpec:
    id: str
    intent: str
    expected_engines: list[str]
    acceptable_alternatives: list[list[str]] = field(default_factory=list)
    expected_params: dict[str, Any] = field(default_factory=dict)
    expected_freshness: str | None = None
    category: str = "single_engine"
    difficulty: str = "medium"
    notes: str = ""


@dataclass(slots=True)
class EvalResult:
    task: TaskSpec
    predicted_engines: list[str]
    predicted_params: dict[str, Any]
    predicted_freshness: str | None
    candidate_count: int
    engines_correct: bool
    params_correct: bool
    freshness_correct: bool
    matched_alternative: bool
    confidence: float
    latency_ms: float
    failure_mode: str | None
    detail: str

    @property
    def correct(self) -> bool:
        return self.engines_correct and self.params_correct


def load_tasks(suite_version: str = "v1") -> list[TaskSpec]:
    path = FIXTURES / ("tasks_" + suite_version + ".json")
    if not path.exists():
        raise FileNotFoundError("Benchmark fixture not found: " + str(path))
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [
        TaskSpec(
            id=row["id"],
            intent=row["intent"],
            expected_engines=list(row.get("expected_engines", [])),
            acceptable_alternatives=[list(a) for a in row.get("acceptable_alternatives", [])],
            expected_params=dict(row.get("expected_params", {})),
            expected_freshness=row.get("expected_freshness"),
            category=row.get("category", "single_engine"),
            difficulty=row.get("difficulty", "medium"),
            notes=row.get("notes", ""),
        )
        for row in payload.get("tasks", [])
    ]


def _engines_match(predicted: list[str], task: TaskSpec) -> tuple[bool, bool]:
    """``(correct, matched_alternative)``.

    The expected chain is ordered; an acceptable alternative counts as correct
    but is recorded separately so the report can show how often the planner
    took a different-but-valid route.
    """
    if predicted == task.expected_engines:
        return True, False
    for alternative in task.acceptable_alternatives:
        if predicted == alternative:
            return True, True
    return False, False


def _params_match(predicted: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if str(predicted.get(key, "")).lower() != str(value).lower():
            return False
    return True


def _classify_failure(predicted: list[str], task: TaskSpec, params_ok: bool) -> str | None:
    if not predicted:
        return "no_plan"
    expected = task.expected_engines
    if predicted == expected:
        return None if params_ok else "locale_miss"
    if set(predicted) == set(expected):
        return "wrong_engine"
    if len(predicted) < len(expected) and predicted == expected[: len(predicted)]:
        return "missing_hop"
    if len(predicted) > len(expected) and predicted[: len(expected)] == expected:
        return "extra_hop"
    return "wrong_engine"


class BenchmarkHarness:
    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        catalog: CatalogIndex | None = None,
        llm: LLMAdapter | None = None,
    ) -> None:
        self.session = session
        self.catalog = catalog or load_catalog()
        self.llm = llm or get_llm()

    # ------------------------------------------------------------ systems
    async def run_serpflow(self, task: TaskSpec) -> EvalResult:
        """The full pipeline: retrieve, select, synthesize, path-find."""
        started = time.perf_counter()
        retrieved = stage_a.retrieve(self.catalog, task.intent)
        selection = await self.llm.select_engines(
            task.intent, [c.to_payload() for c in retrieved], max_select=2
        )
        if not selection.chosen:
            return self._fail(task, started, "selector returned no engine")

        specs = [
            {
                "engine": c.engine,
                "requires": {
                    k: v.model_dump() for k, v in self.catalog.get(c.engine).requires.items()
                },
                "optional": self.catalog.get(c.engine).optional,
                "locale_sensitive": self.catalog.get(c.engine).locale_sensitive,
                "volatility_prior": self.catalog.get(c.engine).volatility_prior,
            }
            for c in selection.chosen
            if self.catalog.has(c.engine)
        ]
        synthesis = await self.llm.synthesize(task.intent, specs)
        available = _available_params(synthesis.parameters)

        # Mirror the planner: generate the candidate set, then rank it the way
        # the planner would with a cold cache. Taking the first path of the
        # first engine would score a different system than the one that ships.
        candidate_set = stage_d.generate(
            self.catalog,
            chosen_engines=[(c.engine, c.confidence) for c in selection.chosen],
            retrieved=retrieved,
            available_params=available,
        )
        candidate_count = candidate_set.count
        answering = [p for p in candidate_set.plans if p.role == ROLE_ANSWER]
        ranked = sorted(
            answering or candidate_set.plans,
            key=lambda p: (
                COVERAGE_RANK.get(p.coverage, 1),
                p.path.naive_cost,
                -p.confidence,
                p.signature,
            ),
        )
        if not ranked:
            return self._fail(task, started, "no valid dependency path", candidate_count)

        predicted = ranked[0].engines
        engines_ok, alternative = _engines_match(predicted, task)
        params_ok = _params_match(synthesis.parameters, task.expected_params)
        freshness_ok = (
            task.expected_freshness is None or synthesis.freshness == task.expected_freshness
        )
        return EvalResult(
            task=task,
            predicted_engines=predicted,
            predicted_params={
                k: v for k, v in synthesis.parameters.items() if k in ("gl", "hl", "location")
            },
            predicted_freshness=synthesis.freshness,
            candidate_count=candidate_count,
            engines_correct=engines_ok,
            params_correct=params_ok,
            freshness_correct=freshness_ok,
            matched_alternative=alternative,
            confidence=selection.confidence,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            failure_mode=None
            if (engines_ok and params_ok)
            else _classify_failure(predicted, task, params_ok),
            detail="chain " + " -> ".join(predicted),
        )

    async def run_embedding_only(self, task: TaskSpec) -> EvalResult:
        """Retrieval with no selector and no path-finding.

        The top embedding match becomes the whole plan, which is what an
        embedding-only system can actually produce. It has no way to discover a
        second hop.
        """
        started = time.perf_counter()
        intent_vector = embed(task.intent)
        best = max(
            self.catalog.engines.items(),
            key=lambda kv: cosine_similarity(intent_vector, embed(kv[1].search_text())),
        )
        predicted = [best[0]]
        engines_ok, alternative = _engines_match(predicted, task)
        return EvalResult(
            task=task,
            predicted_engines=predicted,
            predicted_params={},
            predicted_freshness=None,
            candidate_count=1,
            engines_correct=engines_ok,
            params_correct=not task.expected_params,
            freshness_correct=task.expected_freshness is None,
            matched_alternative=alternative,
            confidence=cosine_similarity(intent_vector, embed(best[1].search_text())),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            failure_mode=None if engines_ok else _classify_failure(predicted, task, True),
            detail="top embedding match only",
        )

    async def run_unaided(self, task: TaskSpec) -> EvalResult:
        """A frontier model writing SerpApi calls with no catalog.

        The model gets the intent and nothing else: no engine list, no
        dependency edges, no substitutes. That is the baseline the README
        compares against, and it is the condition most of the 111-of-185
        community projects are effectively in.
        """
        started = time.perf_counter()
        predicted: list[str] = []
        params: dict[str, Any] = {}
        freshness: str | None = None

        from app.integrations.llm.groq import GroqLLMAdapter

        if isinstance(self.llm, GroqLLMAdapter) and self.llm.configured:
            try:
                raw = await self.llm._complete(
                    (
                        "You write SerpApi requests. Given a search intent, name the SerpApi "
                        "engine or ordered chain of engines you would call, and the locale "
                        "parameters. You have no engine catalog; rely on your own knowledge. "
                        'Respond with JSON only: {"engines":["..."],"params":{"gl":"..",'
                        '"hl":".."},"freshness":"realtime|fresh|recent|stable"}'
                    ),
                    json.dumps({"intent": task.intent}),
                    max_tokens=300,
                )
                predicted = [str(e) for e in (raw.get("engines") or [])][:4]
                params = dict(raw.get("params") or {})
                freshness = raw.get("freshness")
            except Exception as exc:
                log.warning(
                    "unaided baseline call failed",
                    extra={"event": "benchmark.unaided_error", "error": type(exc).__name__},
                )
        else:
            # Without a configured model this baseline reproduces the dominant
            # community behaviour: engine=google for everything.
            predicted = ["google"]
            params = {}
            freshness = None

        engines_ok, alternative = _engines_match(predicted, task)
        params_ok = _params_match(params, task.expected_params)
        return EvalResult(
            task=task,
            predicted_engines=predicted,
            predicted_params=params,
            predicted_freshness=freshness,
            candidate_count=1,
            engines_correct=engines_ok,
            params_correct=params_ok,
            freshness_correct=(
                task.expected_freshness is None or freshness == task.expected_freshness
            ),
            matched_alternative=alternative,
            confidence=0.0,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            failure_mode=None
            if (engines_ok and params_ok)
            else _classify_failure(predicted, task, params_ok),
            detail="no catalog",
        )

    def _fail(
        self, task: TaskSpec, started: float, detail: str, candidate_count: int = 0
    ) -> EvalResult:
        return EvalResult(
            task=task,
            predicted_engines=[],
            predicted_params={},
            predicted_freshness=None,
            candidate_count=candidate_count,
            engines_correct=False,
            params_correct=False,
            freshness_correct=False,
            matched_alternative=False,
            confidence=0.0,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            failure_mode="no_plan",
            detail=detail,
        )

    # ---------------------------------------------------------------- run
    async def run(
        self,
        *,
        system: str = SYSTEM_SERPFLOW,
        suite_version: str = "v1",
        limit: int | None = None,
        persist: bool = True,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        tasks = load_tasks(suite_version)
        if limit:
            tasks = tasks[:limit]

        runner = {
            SYSTEM_SERPFLOW: self.run_serpflow,
            SYSTEM_EMBEDDING: self.run_embedding_only,
            SYSTEM_UNAIDED: self.run_unaided,
        }[system]

        results: list[EvalResult] = []
        for task in tasks:
            results.append(await runner(task))

        report = self.summarize(results, system=system, suite_version=suite_version)

        if persist and self.session is not None:
            run_row = BenchmarkRun(
                org_id=org_id,
                suite_version=suite_version,
                catalog_version=self.catalog.version,
                system=system,
                llm_model=getattr(self.llm, "model", "deterministic"),
                task_count=report["task_count"],
                correct_count=report["correct_count"],
                partial_count=report["partial_count"],
                accuracy=report["accuracy"],
                engine_accuracy=report["engine_accuracy"],
                param_accuracy=report["param_accuracy"],
                freshness_accuracy=report["freshness_accuracy"],
                mean_confidence=report["mean_confidence"],
                mean_latency_ms=report["mean_latency_ms"],
                by_category=report["by_category"],
                failure_modes=report["failure_modes"],
                notes=report["error_analysis"],
                finished_at=datetime.now(UTC),
            )
            self.session.add(run_row)
            await self.session.flush()
            for result in results:
                self.session.add(
                    RoutingEval(
                        benchmark_run_id=run_row.id,
                        task_key=result.task.id,
                        catalog_version=self.catalog.version,
                        system=system,
                        predicted_engines=result.predicted_engines,
                        predicted_params=result.predicted_params,
                        predicted_freshness=result.predicted_freshness,
                        candidate_count=result.candidate_count,
                        engines_correct=result.engines_correct,
                        params_correct=result.params_correct,
                        freshness_correct=result.freshness_correct,
                        matched_alternative=result.matched_alternative,
                        correct=result.correct,
                        confidence=result.confidence,
                        latency_ms=result.latency_ms,
                        failure_mode=result.failure_mode,
                        detail=result.detail[:1000],
                    )
                )
            report["benchmark_run_id"] = run_row.id

        metrics.routing_accuracy.labels(system=system, catalog_version=self.catalog.version).set(
            report["accuracy"]
        )
        return report

    def summarize(
        self, results: list[EvalResult], *, system: str, suite_version: str
    ) -> dict[str, Any]:
        total = len(results) or 1
        correct = sum(1 for r in results if r.correct)
        partial = sum(1 for r in results if r.engines_correct and not r.params_correct)

        by_category: dict[str, dict[str, Any]] = {}
        for result in results:
            bucket = by_category.setdefault(
                result.task.category, {"total": 0, "correct": 0, "accuracy": 0.0}
            )
            bucket["total"] += 1
            bucket["correct"] += int(result.correct)
        for bucket in by_category.values():
            bucket["accuracy"] = round(bucket["correct"] / max(1, bucket["total"]), 4)

        failure_modes: dict[str, int] = {}
        examples: dict[str, list[str]] = {}
        for result in results:
            if result.failure_mode is None:
                continue
            failure_modes[result.failure_mode] = failure_modes.get(result.failure_mode, 0) + 1
            examples.setdefault(result.failure_mode, []).append(
                result.task.id
                + ": expected "
                + " -> ".join(result.task.expected_engines)
                + ", predicted "
                + (" -> ".join(result.predicted_engines) or "(nothing)")
            )

        return {
            "system": system,
            "suite_version": suite_version,
            "catalog_version": self.catalog.version,
            "llm_model": getattr(self.llm, "model", "deterministic"),
            "task_count": len(results),
            "correct_count": correct,
            "partial_count": partial,
            "accuracy": round(correct / total, 4),
            "engine_accuracy": round(sum(1 for r in results if r.engines_correct) / total, 4),
            "param_accuracy": round(sum(1 for r in results if r.params_correct) / total, 4),
            "freshness_accuracy": round(sum(1 for r in results if r.freshness_correct) / total, 4),
            "matched_alternative_count": sum(1 for r in results if r.matched_alternative),
            "mean_confidence": round(sum(r.confidence for r in results) / total, 4),
            "mean_latency_ms": round(sum(r.latency_ms for r in results) / total, 2),
            "mean_candidate_count": round(sum(r.candidate_count for r in results) / total, 2),
            "by_category": by_category,
            "failure_modes": failure_modes,
            "failure_examples": {k: v[:5] for k, v in examples.items()},
            "error_analysis": _error_analysis(failure_modes, by_category),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def load_fixtures_into_db(self, suite_version: str = "v1") -> int:
        if self.session is None:
            return 0
        tasks = load_tasks(suite_version)
        existing = {
            row.task_key
            for row in (
                await self.session.scalars(
                    select(BenchmarkTask).where(BenchmarkTask.suite_version == suite_version)
                )
            ).all()
        }
        added = 0
        for task in tasks:
            if task.id in existing:
                continue
            self.session.add(
                BenchmarkTask(
                    task_key=task.id,
                    suite_version=suite_version,
                    intent=task.intent,
                    expected_engines=task.expected_engines,
                    acceptable_alternatives=task.acceptable_alternatives,
                    expected_params=task.expected_params,
                    expected_freshness=task.expected_freshness,
                    category=task.category,
                    difficulty=task.difficulty,
                    notes=task.notes,
                )
            )
            added += 1
        return added


def _error_analysis(failure_modes: dict[str, int], by_category: dict[str, Any]) -> str:
    if not failure_modes:
        return "No failures on this suite."
    ranked = sorted(failure_modes.items(), key=lambda kv: -kv[1])
    parts = [
        "Dominant failure mode: "
        + ranked[0][0].replace("_", " ")
        + " ("
        + str(ranked[0][1])
        + " tasks)."
    ]
    weakest = min(by_category.items(), key=lambda kv: kv[1]["accuracy"], default=None)
    if weakest:
        parts.append(
            "Weakest category: "
            + weakest[0]
            + " at "
            + str(round(weakest[1]["accuracy"] * 100, 1))
            + "%."
        )
    for mode, count in ranked[1:4]:
        parts.append(mode.replace("_", " ") + ": " + str(count) + ".")
    return " ".join(parts)


def _available_params(parameters: dict[str, Any]) -> set[str]:
    available = {k for k, v in parameters.items() if v not in (None, "")}
    if available & {"q", "query", "text", "search_query", "term", "p", "k", "_nkw"}:
        available |= {
            "q",
            "query",
            "text",
            "search_query",
            "term",
            "p",
            "k",
            "_nkw",
            "find_desc",
            "mauthors",
            "keyword",
        }
    if "location" in available:
        available |= {"find_loc", "l"}
    if "date" in available:
        available |= {"outbound_date", "check_in_date", "check_out_date"}
    return available


def write_report(report: dict[str, Any], *, directory: Path | None = None) -> Path:
    """Commit the result per catalog_version (section 53)."""
    root = directory or (FIXTURES / "results")
    root.mkdir(parents=True, exist_ok=True)
    name = (
        report["catalog_version"] + "_" + report["suite_version"] + "_" + report["system"] + ".json"
    )
    path = root / name
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    return path


__all__ = [
    "FAILURE_MODES",
    "FIXTURES",
    "SYSTEM_EMBEDDING",
    "SYSTEM_SERPFLOW",
    "SYSTEM_UNAIDED",
    "BenchmarkHarness",
    "EvalResult",
    "TaskSpec",
    "load_tasks",
    "write_report",
]
