"""The seed is idempotent against a real database.

The claim `SEED_ON_STARTUP` makes is that it can run on every boot of every
replica without duplicating anything. That is only worth asserting against
PostgreSQL, because what would break is a unique constraint.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db.models.catalog import CatalogEngine
from app.db.models.identity import Organization, Project, User
from app.db.models.keys import ApiKey
from app.db.seed import (
    DEMO_ORG_SLUG,
    benchmarks_are_loaded,
    catalog_is_projected,
    demo_org_exists,
    is_seeded,
    seed_if_absent,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _counts(session) -> dict[str, int]:
    out = {}
    for label, model in (
        ("organizations", Organization),
        ("users", User),
        ("projects", Project),
        ("api_keys", ApiKey),
        ("catalog_engines", CatalogEngine),
    ):
        out[label] = int(await session.scalar(select(func.count()).select_from(model)) or 0)
    return out


async def test_the_test_database_reports_as_seeded(requires_postgres, session):
    """The suite's database is seeded, so every presence check must agree."""
    assert await catalog_is_projected(session) is True
    assert await benchmarks_are_loaded(session) is True
    assert await demo_org_exists(session) is True
    assert await is_seeded(session) is True


async def test_seeding_an_already_seeded_database_is_a_no_op(requires_postgres, session):
    before = await _counts(session)

    outcome = await seed_if_absent(session)

    assert outcome["status"] == "already_seeded"
    assert outcome["seeded"] == []
    assert await _counts(session) == before


async def test_repeated_seeding_never_duplicates(requires_postgres, session):
    """What a restart loop would do. Three passes, same row counts."""
    before = await _counts(session)
    for _ in range(3):
        await seed_if_absent(session)
    assert await _counts(session) == before


async def test_exactly_one_demo_organization_exists(requires_postgres, session):
    count = int(
        await session.scalar(
            select(func.count()).select_from(Organization).where(Organization.slug == DEMO_ORG_SLUG)
        )
        or 0
    )
    assert count == 1
