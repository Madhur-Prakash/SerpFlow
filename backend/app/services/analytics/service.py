"""Analytics (section 52).

Cost attribution::

    Organization -> Project -> Principal -> Run -> Step -> Engine

Savings decomposition::

    Naive execution
            v Routing savings
            v Exact cache savings
            v Semantic cache savings
            v Archive savings
            v Actual spend

Every figure here is computed from the ledger and the run tables. Nothing on
the dashboard is hand-written, which is the exit criterion for section 78
phase 3.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.benchmark import BenchmarkRun
from app.db.models.caching import CacheEntry, FalseHitReport, SemanticGuardRejection, TTLObservation
from app.db.models.governance import Alert, BudgetLedgerEntry
from app.db.models.identity import Project
from app.db.models.keys import UpstreamCredential, UpstreamQuotaSnapshot
from app.db.models.planning import Plan, Run, Step


class AnalyticsService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self.session = session
        self.org_id = org_id

    # ------------------------------------------------------------ overview
    async def dashboard(self, *, days: int = 30) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=days)

        spent = await self._ledger_sum("spend", since=since)
        saved = await self._ledger_sum("saving", since=since)
        layers = await self.cache_layer_distribution(since=since)
        total_lookups = sum(layers.values()) or 1
        hits = total_lookups - layers.get("live", 0)

        replan_changed = int(
            await self.session.scalar(
                select(func.count(Plan.id)).where(
                    Plan.org_id == self.org_id,
                    Plan.marginal_replan_changed_selection.is_(True),
                    Plan.created_at >= since,
                )
            )
            or 0
        )
        plans_total = int(
            await self.session.scalar(
                select(func.count(Plan.id)).where(
                    Plan.org_id == self.org_id, Plan.created_at >= since
                )
            )
            or 0
        )

        return {
            "window_days": days,
            "credits_spent": spent,
            "credits_saved": saved,
            "savings_ratio": round(saved / max(1, spent + saved), 4),
            "cache_hit_rate": round(hits / total_lookups, 4),
            "cache_layers": layers,
            "runs": await self.run_counts(since=since),
            "spend_by_project": await self.spend_by_project(since=since),
            "recent_runs": await self.recent_runs(limit=8),
            "active_alerts": await self.active_alerts(limit=5),
            "upstream_quota": await self.upstream_quota(),
            "projected_exhaustion": None,
            "cross_project_benefit": await self.cross_project_benefit(since=since),
            "marginal_replanning": {
                "plans_total": plans_total,
                "selection_changed": replan_changed,
                "selection_changed_ratio": round(replan_changed / max(1, plans_total), 4),
            },
        }

    async def _ledger_sum(
        self, kind: str, *, since: datetime | None = None, project_id: str | None = None
    ) -> int:
        query = select(func.coalesce(func.sum(BudgetLedgerEntry.credits), 0)).where(
            BudgetLedgerEntry.org_id == self.org_id, BudgetLedgerEntry.kind == kind
        )
        if since:
            query = query.where(BudgetLedgerEntry.created_at >= since)
        if project_id:
            column = (
                BudgetLedgerEntry.beneficiary_project_id
                if kind == "saving"
                else BudgetLedgerEntry.project_id
            )
            query = query.where(column == project_id)
        return int(await self.session.scalar(query) or 0)

    # ------------------------------------------------------------- savings
    async def savings_decomposition(self, *, days: int = 30) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=days)
        rows = (
            await self.session.execute(
                select(
                    BudgetLedgerEntry.source,
                    func.coalesce(func.sum(BudgetLedgerEntry.credits), 0),
                )
                .where(
                    BudgetLedgerEntry.org_id == self.org_id,
                    BudgetLedgerEntry.kind == "saving",
                    BudgetLedgerEntry.created_at >= since,
                )
                .group_by(BudgetLedgerEntry.source)
            )
        ).all()
        by_source = {str(source): int(total) for source, total in rows}
        spend = await self._ledger_sum("spend", since=since)

        naive = (
            spend
            + by_source.get("routing", 0)
            + by_source.get("exact", 0)
            + by_source.get("semantic", 0)
            + by_source.get("archive", 0)
        )

        # Waterfall, in the order section 52 specifies.
        steps = [
            {"label": "Naive execution", "value": naive, "kind": "base"},
            {"label": "Routing savings", "value": -by_source.get("routing", 0), "kind": "saving"},
            {"label": "Exact cache savings", "value": -by_source.get("exact", 0), "kind": "saving"},
            {
                "label": "Semantic cache savings",
                "value": -by_source.get("semantic", 0),
                "kind": "saving",
            },
            {"label": "Archive savings", "value": -by_source.get("archive", 0), "kind": "saving"},
            {"label": "Actual spend", "value": spend, "kind": "total"},
        ]
        return {
            "window_days": days,
            "naive_execution": naive,
            "actual_spend": spend,
            "total_saved": naive - spend,
            "by_source": by_source,
            "waterfall": steps,
        }

    async def spend_by_project(self, *, since: datetime | None = None) -> list[dict[str, Any]]:
        projects = {
            p.id: p.name
            for p in (
                await self.session.scalars(select(Project).where(Project.org_id == self.org_id))
            ).all()
        }
        spend_query = select(
            BudgetLedgerEntry.project_id, func.coalesce(func.sum(BudgetLedgerEntry.credits), 0)
        ).where(BudgetLedgerEntry.org_id == self.org_id, BudgetLedgerEntry.kind == "spend")
        saving_query = select(
            BudgetLedgerEntry.beneficiary_project_id,
            func.coalesce(func.sum(BudgetLedgerEntry.credits), 0),
        ).where(BudgetLedgerEntry.org_id == self.org_id, BudgetLedgerEntry.kind == "saving")
        if since:
            spend_query = spend_query.where(BudgetLedgerEntry.created_at >= since)
            saving_query = saving_query.where(BudgetLedgerEntry.created_at >= since)

        spend = {
            str(pid): int(total)
            for pid, total in (
                await self.session.execute(spend_query.group_by(BudgetLedgerEntry.project_id))
            ).all()
        }
        saved = {
            str(pid): int(total)
            for pid, total in (
                await self.session.execute(
                    saving_query.group_by(BudgetLedgerEntry.beneficiary_project_id)
                )
            ).all()
            if pid
        }
        out = []
        for project_id, name in projects.items():
            out.append(
                {
                    "project_id": project_id,
                    "project_name": name,
                    "spent": spend.get(project_id, 0),
                    "saved": saved.get(project_id, 0),
                }
            )
        return sorted(out, key=lambda r: -r["spent"])

    async def cross_project_benefit(self, *, since: datetime | None = None) -> dict[str, Any]:
        """Section 37: one project's spend benefiting another.

        SPEND is attributed to the fetching project; SAVINGS to the
        beneficiary. The rows where those differ are exactly the cross-project
        benefit, which is why both columns exist on the ledger.
        """
        query = select(
            BudgetLedgerEntry.project_id,
            BudgetLedgerEntry.beneficiary_project_id,
            func.coalesce(func.sum(BudgetLedgerEntry.credits), 0),
        ).where(
            BudgetLedgerEntry.org_id == self.org_id,
            BudgetLedgerEntry.kind == "saving",
            BudgetLedgerEntry.beneficiary_project_id.is_not(None),
            BudgetLedgerEntry.project_id != BudgetLedgerEntry.beneficiary_project_id,
        )
        if since:
            query = query.where(BudgetLedgerEntry.created_at >= since)
        rows = (
            await self.session.execute(
                query.group_by(
                    BudgetLedgerEntry.project_id, BudgetLedgerEntry.beneficiary_project_id
                )
            )
        ).all()
        names = {
            p.id: p.name
            for p in (
                await self.session.scalars(select(Project).where(Project.org_id == self.org_id))
            ).all()
        }
        flows = [
            {
                "fetching_project_id": str(src),
                "fetching_project_name": names.get(str(src), str(src)),
                "beneficiary_project_id": str(dst),
                "beneficiary_project_name": names.get(str(dst), str(dst)),
                "credits": int(total),
            }
            for src, dst, total in rows
        ]
        return {"total_credits": sum(f["credits"] for f in flows), "flows": flows}

    # --------------------------------------------------------------- cache
    async def cache_layer_distribution(self, *, since: datetime | None = None) -> dict[str, int]:
        query = select(Step.cache_layer, func.count(Step.id)).where(Step.org_id == self.org_id)
        if since:
            query = query.where(Step.created_at >= since)
        rows = (await self.session.execute(query.group_by(Step.cache_layer))).all()
        out = {"exact": 0, "semantic": 0, "archive": 0, "live": 0, "mock": 0, "replay": 0}
        for layer, count in rows:
            if layer:
                out[str(layer)] = out.get(str(layer), 0) + int(count)
        return out

    async def cache_dashboard(self, *, days: int = 30) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=days)
        layers = await self.cache_layer_distribution(since=since)
        total = sum(layers.values()) or 1
        hits = total - layers.get("live", 0)

        entries = int(
            await self.session.scalar(
                select(func.count(CacheEntry.id)).where(
                    CacheEntry.org_id == self.org_id, CacheEntry.invalidated_at.is_(None)
                )
            )
            or 0
        )
        bytes_stored = int(
            await self.session.scalar(
                select(func.coalesce(func.sum(CacheEntry.payload_bytes), 0)).where(
                    CacheEntry.org_id == self.org_id
                )
            )
            or 0
        )
        partitions = (
            await self.session.execute(
                select(CacheEntry.partition_key, func.count(CacheEntry.id))
                .where(CacheEntry.org_id == self.org_id)
                .group_by(CacheEntry.partition_key)
            )
        ).all()
        guard_rows = (
            await self.session.execute(
                select(SemanticGuardRejection.reason, func.count(SemanticGuardRejection.id))
                .where(
                    SemanticGuardRejection.org_id == self.org_id,
                    SemanticGuardRejection.created_at >= since,
                )
                .group_by(SemanticGuardRejection.reason)
            )
        ).all()
        by_engine = (
            await self.session.execute(
                select(
                    CacheEntry.engine,
                    func.count(CacheEntry.id),
                    func.coalesce(func.sum(CacheEntry.hit_count), 0),
                    func.avg(cast(CacheEntry.ttl_seconds, Float)),
                )
                .where(CacheEntry.org_id == self.org_id, CacheEntry.invalidated_at.is_(None))
                .group_by(CacheEntry.engine)
                .order_by(func.count(CacheEntry.id).desc())
                .limit(25)
            )
        ).all()
        false_hits = int(
            await self.session.scalar(
                select(func.count(FalseHitReport.id)).where(
                    FalseHitReport.org_id == self.org_id, FalseHitReport.created_at >= since
                )
            )
            or 0
        )

        return {
            "window_days": days,
            "layers": layers,
            "hit_rate": round(hits / total, 4),
            "entries": entries,
            "bytes_stored": bytes_stored,
            "partitions": [
                {"partition_key": str(key), "entries": int(count)} for key, count in partitions
            ],
            "guard_rejections": {
                "total": sum(int(c) for _, c in guard_rows),
                "by_reason": {str(reason): int(count) for reason, count in guard_rows},
            },
            "false_hit_reports": false_hits,
            "by_engine": [
                {
                    "engine": str(engine),
                    "entries": int(count),
                    "hits": int(hit_total),
                    "mean_ttl_seconds": round(float(avg_ttl or 0), 1),
                }
                for engine, count, hit_total, avg_ttl in by_engine
            ],
        }

    async def volatility(self, *, days: int = 90) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=days)
        rows = (
            await self.session.execute(
                select(
                    TTLObservation.engine,
                    TTLObservation.query_class,
                    func.count(TTLObservation.id),
                    func.avg(cast(TTLObservation.new_ttl_seconds, Float)),
                    func.avg(cast(TTLObservation.churn_ratio, Float)),
                    func.avg(cast(TTLObservation.observed_interval_seconds, Float)),
                )
                .where(TTLObservation.org_id == self.org_id, TTLObservation.created_at >= since)
                .group_by(TTLObservation.engine, TTLObservation.query_class)
                .order_by(func.count(TTLObservation.id).desc())
                .limit(50)
            )
        ).all()
        directions = (
            await self.session.execute(
                select(TTLObservation.direction, func.count(TTLObservation.id))
                .where(TTLObservation.org_id == self.org_id, TTLObservation.created_at >= since)
                .group_by(TTLObservation.direction)
            )
        ).all()
        return {
            "window_days": days,
            "by_engine_class": [
                {
                    "engine": str(engine),
                    "query_class": str(klass),
                    "observations": int(count),
                    "mean_ttl_seconds": round(float(ttl or 0), 1),
                    "mean_churn": round(float(churn or 0), 4),
                    "measured_refresh_interval_seconds": round(float(interval or 0), 1),
                }
                for engine, klass, count, ttl, churn, interval in rows
            ],
            "ttl_movement": {str(d): int(c) for d, c in directions},
        }

    # ------------------------------------------------------------- routing
    async def routing_quality(self) -> dict[str, Any]:
        runs = (
            await self.session.scalars(
                select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).limit(20)
            )
        ).all()
        by_version: dict[str, dict[str, Any]] = {}
        for run in runs:
            bucket = by_version.setdefault(
                run.catalog_version, {"catalog_version": run.catalog_version, "systems": {}}
            )
            if run.system not in bucket["systems"]:
                bucket["systems"][run.system] = {
                    "accuracy": round(run.accuracy, 4),
                    "engine_accuracy": round(run.engine_accuracy, 4),
                    "param_accuracy": round(run.param_accuracy, 4),
                    "freshness_accuracy": round(run.freshness_accuracy, 4),
                    "task_count": run.task_count,
                    "mean_confidence": round(run.mean_confidence, 4),
                    "failure_modes": run.failure_modes,
                    "run_id": run.id,
                    "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                }

        confidence = await self.session.execute(
            select(
                func.avg(cast(Plan.confidence, Float)),
                func.avg(cast(Plan.candidate_count, Float)),
                func.count(Plan.id),
            ).where(Plan.org_id == self.org_id)
        )
        avg_conf, avg_candidates, plan_count = confidence.one()
        # Every candidate beyond the winner is a rejected alternative, and
        # candidate_count is a plain integer column, so this avoids a
        # JSON-array aggregate that would differ between backends.
        rejected = int(
            await self.session.scalar(
                select(
                    func.coalesce(func.sum(func.greatest(Plan.candidate_count - 1, 0)), 0)
                ).where(Plan.org_id == self.org_id)
            )
            or 0
        )

        return {
            "benchmarks": list(by_version.values()),
            "live": {
                "plans": int(plan_count or 0),
                "mean_confidence": round(float(avg_conf or 0), 4),
                "mean_candidate_count": round(float(avg_candidates or 0), 2),
                "rejected_alternatives": rejected,
            },
        }

    async def engine_reach(self, *, catalog_engine_count: int) -> dict[str, Any]:
        rows = (
            await self.session.execute(
                select(Step.engine, func.count(Step.id))
                .where(Step.org_id == self.org_id)
                .group_by(Step.engine)
                .order_by(func.count(Step.id).desc())
            )
        ).all()
        used = [{"engine": str(e), "calls": int(c)} for e, c in rows]
        return {
            "catalog_engines": catalog_engine_count,
            "engines_used": len(used),
            "reach_ratio": round(len(used) / max(1, catalog_engine_count), 4),
            "usage": used,
        }

    # --------------------------------------------------------------- misc
    async def run_counts(self, *, since: datetime | None = None) -> dict[str, int]:
        query = select(Run.status, func.count(Run.id)).where(Run.org_id == self.org_id)
        if since:
            query = query.where(Run.created_at >= since)
        rows = (await self.session.execute(query.group_by(Run.status))).all()
        return {str(status): int(count) for status, count in rows}

    async def recent_runs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = (
            await self.session.scalars(
                select(Run)
                .where(Run.org_id == self.org_id)
                .order_by(Run.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [
            {
                "id": r.id,
                "intent": r.intent[:120],
                "status": r.status,
                "credits_spent": r.credits_spent,
                "credits_saved": r.credits_saved,
                "naive_cost": r.naive_cost,
                "marginal_cost": r.marginal_cost,
                "mode": r.mode,
                "duration_ms": round(r.duration_ms, 1),
                "created_at": r.created_at.isoformat(),
                "project_id": r.project_id,
            }
            for r in rows
        ]

    async def active_alerts(self, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = (
            await self.session.scalars(
                select(Alert)
                .where(Alert.org_id == self.org_id, Alert.status == "open")
                .order_by(Alert.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [
            {
                "id": a.id,
                "kind": a.kind,
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "created_at": a.created_at.isoformat(),
                "project_id": a.project_id,
            }
            for a in rows
        ]

    async def upstream_quota(self) -> list[dict[str, Any]]:
        """Internal ledger alongside upstream quota, never merged (section 40)."""
        credentials = (
            await self.session.scalars(
                select(UpstreamCredential).where(
                    UpstreamCredential.org_id == self.org_id,
                    UpstreamCredential.revoked_at.is_(None),
                )
            )
        ).all()
        out: list[dict[str, Any]] = []
        for credential in credentials:
            snapshot = await self.session.scalar(
                select(UpstreamQuotaSnapshot)
                .where(UpstreamQuotaSnapshot.credential_id == credential.id)
                .order_by(UpstreamQuotaSnapshot.created_at.desc())
                .limit(1)
            )
            out.append(
                {
                    "credential_id": credential.id,
                    "name": credential.name,
                    "fingerprint": credential.fingerprint,
                    "upstream_plan": credential.upstream_plan,
                    "upstream_searches_left": credential.upstream_searches_left,
                    "upstream_checked_at": (
                        credential.upstream_checked_at.isoformat()
                        if credential.upstream_checked_at
                        else None
                    ),
                    "divergence": snapshot.divergence if snapshot else None,
                    "internal_spend_since_last": (
                        snapshot.internal_spend_since_last if snapshot else None
                    ),
                    "upstream_spend_since_last": (
                        snapshot.upstream_spend_since_last if snapshot else None
                    ),
                }
            )
        return out

    async def cost_attribution(self, *, days: int = 30) -> dict[str, Any]:
        """Organization -> Project -> Principal -> Run -> Step -> Engine."""
        since = datetime.now(UTC) - timedelta(days=days)
        rows = (
            await self.session.execute(
                select(
                    Run.project_id,
                    Run.principal_id,
                    Run.id,
                    Step.engine,
                    func.coalesce(func.sum(Step.credits), 0),
                )
                .select_from(Step)
                .join(Run, and_(Step.run_id == Run.id))
                .where(Run.org_id == self.org_id, Run.created_at >= since)
                .group_by(Run.project_id, Run.principal_id, Run.id, Step.engine)
                .order_by(func.sum(Step.credits).desc())
                .limit(500)
            )
        ).all()
        return {
            "window_days": days,
            "rows": [
                {
                    "project_id": str(project_id),
                    "principal_id": str(principal_id) if principal_id else None,
                    "run_id": str(run_id),
                    "engine": str(engine),
                    "credits": int(credits),
                }
                for project_id, principal_id, run_id, engine, credits in rows
            ],
        }


__all__ = ["AnalyticsService"]
