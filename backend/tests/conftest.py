"""Shared test fixtures.

Unit tests need no services. Integration and e2e tests need PostgreSQL with
pgvector and Redis, and skip themselves cleanly when those are not reachable,
so ``make test`` is useful on a laptop with nothing running.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

os.environ.setdefault("SERPFLOW_MODE", "replay")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("KAFKA_ENABLED", "false")

from app.core.config import settings  # noqa: E402
from app.db.session import get_sessionmaker, set_tenant  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires postgres/redis")
    config.addinivalue_line("markers", "e2e: full end-to-end flow")


async def _postgres_available() -> bool:
    from app.db.session import ping

    try:
        return await ping()
    except Exception:
        return False


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    return (
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_postgres_available())
    )


@pytest.fixture
def requires_postgres(postgres_available: bool) -> None:
    if not postgres_available:
        pytest.skip("PostgreSQL is not reachable; run `make up` first.")


@pytest_asyncio.fixture
async def session() -> AsyncIterator:
    """A transactional session, rolled back at the end of the test."""
    maker = get_sessionmaker()
    async with maker() as db:
        try:
            yield db
        finally:
            await db.rollback()


@pytest_asyncio.fixture
async def org_fixture(session) -> AsyncIterator[dict]:
    """A throwaway organization, project and both API key kinds."""
    from app.services.auth.service import AuthService
    from app.services.budgets.service import ensure_budget

    suffix = uuid.uuid4().hex[:8]
    auth = AuthService(session)
    user, org, _ = await auth.register(
        email="test-" + suffix + "@serpflow-tests.dev",
        password="test-password-123",
        full_name="Test Owner",
        org_name="Test Org " + suffix,
    )
    await set_tenant(session, org.id)
    project = await auth.create_project(org_id=org.id, name="Test Project")
    await ensure_budget(
        session,
        org_id=org.id,
        scope="project",
        scope_id=project.id,
        limit_credits=250,
        name="test budget",
    )
    test_row, test_key = await auth.create_api_key(
        org_id=org.id, project=project, name="test key", environment="test"
    )
    live_row, live_key = await auth.create_api_key(
        org_id=org.id, project=project, name="live key", environment="live"
    )
    await session.flush()

    yield {
        "user": user,
        "org": org,
        "project": project,
        "test_key_row": test_row,
        "test_key": test_key.plaintext,
        "live_key_row": live_row,
        "live_key": live_key.plaintext,
    }


@pytest.fixture
def test_principal(org_fixture):
    from app.core.permissions import permissions_for
    from app.services.auth.service import Principal

    row = org_fixture["test_key_row"]
    return Principal(
        id=row.id,
        type="api_key",
        org_id=org_fixture["org"].id,
        project_id=org_fixture["project"].id,
        role=row.role,
        api_key_id=row.id,
        key_environment="test",
        permissions=permissions_for(row.role),
    )


@pytest.fixture
def catalog():
    from app.services.catalog.loader import load_catalog

    return load_catalog()


@pytest.fixture
def settings_fixture():
    return settings
