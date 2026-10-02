"""Seeding a working SerpFlow instance.

Runs after migrations and needs no API keys of any kind (section 41):

  * projects the committed YAML catalog into the queryable catalog tables
  * loads the 120 committed benchmark fixtures
  * creates a demo organization, two users with different roles, two projects,
    budgets sized to the SerpApi 250-search free tier, and both a live and a
    test API key

The implementation lives in the package rather than in ``scripts/`` because two
callers need it: ``scripts/seed.py`` (``make seed``) and the application's own
startup bootstrap, which seeds an empty database when ``SEED_ON_STARTUP`` is
set. See ``app/db/bootstrap.py``.

Every step is idempotent. ``seed_if_absent`` additionally checks before doing
any work, so it is safe to run on every boot and on every replica.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select

from app.core.logging import get_logger
from app.core.security import encrypt_credential
from app.db.models.benchmark import BenchmarkTask
from app.db.models.catalog import (
    CatalogEdge,
    CatalogEngine,
    CatalogSubstitute,
    CatalogVersion,
)
from app.db.models.identity import Membership, Organization, User
from app.db.models.keys import UpstreamCredential
from app.integrations.llm.embedding import embed
from app.services.audit.service import AuditService
from app.services.auth.service import AuthService
from app.services.benchmark.service import BenchmarkHarness
from app.services.budgets.service import ensure_budget
from app.services.catalog.loader import load_catalog

log = get_logger("serpflow.seed")


DEMO_ORG_SLUG = "serpflow-demo"
OWNER_EMAIL = "owner@serpflow.dev"
ANALYST_EMAIL = "analyst@serpflow.dev"
DEMO_PASSWORD = "serpflow-demo-2026"

# The SerpApi free tier is 250 searches. Every default here is sized so the
# full demo fits inside it with room to spare.
FREE_TIER_SEARCHES = 250
DEMO_PROJECT_BUDGET = 60
# Market Watch is sized for the full-scale reference chain (101 credits). That
# chain is only ever executed against the deterministic mock or replayed from a
# recorded cassette - section 70 is explicit that it must never run live,
# because one run would consume 40% of the SerpApi free tier.
WARMUP_PROJECT_BUDGET = 150
DEMO_SESSION_CAP = 20


async def project_catalog(session) -> dict:
    """Project the committed YAML catalog into the queryable tables."""
    index = load_catalog()

    await session.execute(
        delete(CatalogEngine).where(CatalogEngine.catalog_version == index.version)
    )
    await session.execute(delete(CatalogEdge).where(CatalogEdge.catalog_version == index.version))
    await session.execute(
        delete(CatalogSubstitute).where(CatalogSubstitute.catalog_version == index.version)
    )

    for name, spec in index.engines.items():
        search_text = spec.search_text()
        session.add(
            CatalogEngine(
                catalog_version=index.version,
                engine=name,
                purpose=spec.purpose,
                capability_tags=spec.capability_tags,
                requires={k: v.model_dump() for k, v in spec.requires.items()},
                optional_params=spec.optional,
                produces={k: v.model_dump() for k, v in spec.produces.items()},
                cost=spec.cost,
                latency_class=spec.latency_class,
                volatility_prior=spec.volatility_prior,
                locale_sensitive=spec.locale_sensitive,
                pii_risk=spec.pii_risk,
                docs_url=spec.docs_url,
                search_text=search_text,
                embedding=list(embed(search_text)),
                raw=spec.model_dump(),
            )
        )

    for edge in index.edges:
        session.add(
            CatalogEdge(
                catalog_version=index.version,
                from_engine=edge.from_engine,
                to_engine=edge.to_engine,
                produces_field=edge.produces_field,
                satisfies_param=edge.satisfies_param,
                param_type=edge.param_type,
                fan_out_hint=edge.fan_out_hint,
                note=edge.note,
            )
        )

    for sub in index.substitutes:
        session.add(
            CatalogSubstitute(
                catalog_version=index.version,
                engine=sub.engine,
                substitute_engine=sub.substitute_engine,
                coverage=sub.coverage,
                note=sub.note,
                shared_tags=sub.shared_tags,
                confidence_penalty=sub.confidence_penalty,
            )
        )

    existing = await session.scalar(
        select(CatalogVersion).where(CatalogVersion.version == index.version)
    )
    stats = index.stats()
    if existing is None:
        session.add(
            CatalogVersion(
                version=index.version,
                engine_count=stats["engines"],
                edge_count=stats["edges"],
                substitute_count=stats["substitutes"],
                capability_tag_count=stats["capability_tags"],
                checksum=index.checksum,
                notes=index.meta.notes,
            )
        )
    else:
        existing.engine_count = stats["engines"]
        existing.edge_count = stats["edges"]
        existing.substitute_count = stats["substitutes"]
        existing.capability_tag_count = stats["capability_tags"]
        existing.checksum = index.checksum

    await session.flush()
    return {"catalog_version": index.version, **stats}


async def load_benchmarks(session) -> int:
    harness = BenchmarkHarness(session)
    return await harness.load_fixtures_into_db("v1")


async def reset_demo(session) -> None:
    org = await session.scalar(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
    if org is None:
        return
    # The audit log is append-only at the database level, so a cascade delete
    # has to opt in explicitly for this transaction.
    await AuditService(session, org_id=org.id).allow_purge()
    # Break the organization -> credential pointer before cascade delete so the
    # SET NULL side of the cycle does not fight the CASCADE side.
    org.default_credential_id = None
    await session.flush()
    await session.delete(org)
    for email in (OWNER_EMAIL, ANALYST_EMAIL):
        user = await session.scalar(select(User).where(User.email == email))
        if user is not None:
            await session.delete(user)
    await session.flush()
    log.info("demo organization reset", extra={"event": "seed.reset"})


async def seed_demo(session) -> dict:
    auth = AuthService(session)

    existing = await session.scalar(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
    if existing is not None:
        return {"status": "exists", "org_id": existing.id}

    owner = await session.scalar(select(User).where(User.email == OWNER_EMAIL))
    if owner is None:
        owner, org, _ = await auth.register(
            email=OWNER_EMAIL,
            password=DEMO_PASSWORD,
            full_name="Demo Owner",
            org_name="SerpFlow Demo",
        )
        org.slug = DEMO_ORG_SLUG
        owner.email_verified = True
    else:
        org = Organization(name="SerpFlow Demo", slug=DEMO_ORG_SLUG)
        session.add(org)
        await session.flush()
        session.add(
            Membership(org_id=org.id, user_id=owner.id, role="owner", accepted_at=datetime.now(UTC))
        )

    # A second member with a different role, so the permission boundary is
    # visible immediately: an analyst can plan but not execute.
    analyst = await session.scalar(select(User).where(User.email == ANALYST_EMAIL))
    if analyst is None:
        from app.core.security import hash_password

        analyst = User(
            email=ANALYST_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            full_name="Demo Analyst",
            email_verified=True,
        )
        session.add(analyst)
        await session.flush()
    session.add(
        Membership(org_id=org.id, user_id=analyst.id, role="analyst", accepted_at=datetime.now(UTC))
    )
    await session.flush()

    research = await auth.create_project(
        org_id=org.id,
        name="Review Intelligence",
        slug="review-intelligence",
        description=(
            "The reference demo project: coordinated review ring detection across "
            "Koramangala cafes."
        ),
    )
    market = await auth.create_project(
        org_id=org.id,
        name="Market Watch",
        slug="market-watch",
        description="Second project, used to demonstrate cross-project cache benefit.",
    )

    await ensure_budget(
        session,
        org_id=org.id,
        scope="organization",
        scope_id=org.id,
        limit_credits=FREE_TIER_SEARCHES,
        name="Free tier guard",
        on_exhausted="error",
    )
    await ensure_budget(
        session,
        org_id=org.id,
        scope="project",
        scope_id=research.id,
        limit_credits=DEMO_PROJECT_BUDGET,
        name="Review Intelligence budget",
    )
    await ensure_budget(
        session,
        org_id=org.id,
        scope="project",
        scope_id=market.id,
        limit_credits=WARMUP_PROJECT_BUDGET,
        name="Market Watch budget",
    )

    # A placeholder vault entry so the credential surfaces render with real
    # data. It is a deterministic non-key string, never validated upstream, and
    # it is only reachable by live-key execution - which the demo does not use.
    envelope = encrypt_credential("demo-placeholder-not-a-real-serpapi-key")
    credential = UpstreamCredential(
        org_id=org.id,
        name="Demo placeholder (not validated)",
        ciphertext=envelope.ciphertext,
        encrypted_dek=envelope.encrypted_dek,
        kek_id=envelope.kek_id,
        algo=envelope.algo,
        fingerprint=envelope.fingerprint,
        validation_status="pending",
        validation_error="Placeholder credential; attach a real key to run live.",
    )
    session.add(credential)
    await session.flush()
    org.default_credential_id = credential.id

    test_key_row, test_key = await auth.create_api_key(
        org_id=org.id,
        project=research,
        name="Demo test key",
        environment="test",
        role="developer",
        created_by=owner.id,
    )
    live_key_row, live_key = await auth.create_api_key(
        org_id=org.id,
        project=research,
        name="Demo live key",
        environment="live",
        role="developer",
        created_by=owner.id,
    )
    agent_key_row, agent_key = await auth.create_api_key(
        org_id=org.id,
        project=research,
        name="Demo MCP service principal",
        environment="test",
        role="service",
        created_by=owner.id,
        is_service_principal=True,
        session_cap=DEMO_SESSION_CAP,
    )
    await ensure_budget(
        session,
        org_id=org.id,
        scope="api_key",
        scope_id=agent_key_row.id,
        limit_credits=DEMO_SESSION_CAP,
        name="MCP service principal cap",
    )

    market_test_row, market_test_key = await auth.create_api_key(
        org_id=org.id,
        project=market,
        name="Market Watch test key",
        environment="test",
        role="developer",
        created_by=owner.id,
    )

    return {
        "status": "created",
        "org_id": org.id,
        "owner_email": OWNER_EMAIL,
        "analyst_email": ANALYST_EMAIL,
        "password": DEMO_PASSWORD,
        "projects": {
            "review_intelligence": research.id,
            "market_watch": market.id,
        },
        "keys": {
            "test": test_key.plaintext,
            "live": live_key.plaintext,
            "service": agent_key.plaintext,
            "market_test": market_test_key.plaintext,
        },
        "key_ids": {
            "test": test_key_row.id,
            "live": live_key_row.id,
            "service": agent_key_row.id,
            "market_test": market_test_row.id,
        },
        "credential_fingerprint": credential.fingerprint,
    }


# --------------------------------------------------------------------------
# Presence checks - what "already seeded" means
# --------------------------------------------------------------------------
async def catalog_is_projected(session) -> bool:
    """True when the committed catalog version already has rows."""
    index = load_catalog()
    count = await session.scalar(
        select(func.count())
        .select_from(CatalogEngine)
        .where(CatalogEngine.catalog_version == index.version)
    )
    return bool(count)


async def benchmarks_are_loaded(session, suite_version: str = "v1") -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(BenchmarkTask)
        .where(BenchmarkTask.suite_version == suite_version)
    )
    return bool(count)


async def demo_org_exists(session) -> bool:
    org = await session.scalar(select(Organization.id).where(Organization.slug == DEMO_ORG_SLUG))
    return org is not None


async def is_seeded(session) -> bool:
    """All three are present, so there is nothing for a bootstrap to do."""
    return (
        await catalog_is_projected(session)
        and await benchmarks_are_loaded(session)
        and await demo_org_exists(session)
    )


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------
async def seed_all(session, *, reset: bool = False) -> dict[str, Any]:
    """Seed unconditionally. Backs ``make seed``."""
    if reset:
        await reset_demo(session)
    catalog = await project_catalog(session)
    tasks = await load_benchmarks(session)
    demo = await seed_demo(session)
    return {"catalog": catalog, "tasks": tasks, "demo": demo}


async def seed_if_absent(session) -> dict[str, Any]:
    """Seed only the parts that are missing.

    Safe to call on every boot. Each of the three steps is skipped when its
    data is already present, so a restart against a populated database does no
    writes at all and a half-seeded database is completed rather than
    duplicated.
    """
    actions: list[str] = []

    if await catalog_is_projected(session):
        catalog = None
    else:
        catalog = await project_catalog(session)
        actions.append("catalog")

    if await benchmarks_are_loaded(session):
        tasks = 0
    else:
        try:
            tasks = await load_benchmarks(session)
            actions.append("benchmarks")
        except FileNotFoundError as exc:
            # The benchmark suite is reference data for one dashboard, not
            # something serving a search depends on. A missing fixture file is
            # worth a warning; it is not worth refusing to start.
            tasks = 0
            log.warning(
                "benchmark fixtures unavailable; skipping that part of the seed",
                extra={"event": "seed.benchmarks_skipped", "error": str(exc)},
            )

    if await demo_org_exists(session):
        demo: dict[str, Any] = {"status": "exists"}
    else:
        demo = await seed_demo(session)
        actions.append("demo")

    return {
        "status": "seeded" if actions else "already_seeded",
        "seeded": actions,
        "catalog": catalog,
        "tasks": tasks,
        "demo": demo,
    }


__all__ = [
    "ANALYST_EMAIL",
    "DEMO_ORG_SLUG",
    "DEMO_PASSWORD",
    "DEMO_SESSION_CAP",
    "OWNER_EMAIL",
    "benchmarks_are_loaded",
    "catalog_is_projected",
    "demo_org_exists",
    "is_seeded",
    "load_benchmarks",
    "project_catalog",
    "reset_demo",
    "seed_all",
    "seed_demo",
    "seed_if_absent",
]
