"""Startup bootstrap: migrations and seeding, both opt-in by environment variable.

    RUN_MIGRATIONS_ON_STARTUP=true    apply Alembic migrations before serving
    SEED_ON_STARTUP=true              insert only the data that is missing

Both default to **false**, so the behaviour of an existing deployment does not
change by upgrading. Enabling them turns a fresh database plus a container into
a working instance with no orchestration step in between, which is what the
compose stack does.

Three things make this safe to leave on:

**An advisory lock.** Several API replicas starting together would otherwise
race: two concurrent ``alembic upgrade head`` runs against one database, or two
seeds inserting the same demo organization. One process takes a PostgreSQL
advisory lock and the rest block until it is done, then find the work already
complete. The lock is session-scoped on a dedicated connection and is released
in a ``finally``, so a crash mid-migration frees it when the connection drops.

**Idempotence.** Seeding checks before it writes. A populated database costs
three ``SELECT count(*)`` queries and no writes at all; a half-seeded one is
completed rather than duplicated. See :mod:`app.db.seed`.

**An environment refusal.** ``SEED_ON_STARTUP`` is ignored when ``ENVIRONMENT``
is staging or production. The seed creates demo accounts whose password is
committed to this repository, so the refusal belongs here rather than in
whoever writes the deployment manifest.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_engine, session_scope

log = get_logger("serpflow.bootstrap")

# Two arbitrary but fixed keys. PostgreSQL advisory locks are a global 64-bit
# namespace shared by everything on the database, so they are derived from a
# constant rather than from a hash that could collide with another application.
MIGRATION_LOCK_KEY = 0x5E89_F10C_0001
SEED_LOCK_KEY = 0x5E89_F10C_0002

# backend/ - the directory holding alembic.ini, from app/db/bootstrap.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


class _AdvisoryLock:
    """A session-scoped PostgreSQL advisory lock on its own connection.

    Blocking, not ``try``: a replica that cannot get the lock must wait for the
    migration to finish rather than start serving against a schema that is
    still being changed.
    """

    def __init__(self, key: int) -> None:
        self.key = key
        self._conn: Any = None

    async def __aenter__(self) -> _AdvisoryLock:
        self._conn = await get_engine().connect()
        await self._conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": self.key})
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._conn is None:
            return
        try:
            await self._conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": self.key})
        finally:
            await self._conn.close()
            self._conn = None


def _upgrade_sync() -> None:
    """Run ``alembic upgrade head``.

    Alembic's online path calls ``asyncio.run`` itself, so this cannot execute
    on the running event loop. The caller hands it to a worker thread, where it
    gets a loop of its own.
    """
    from alembic.config import Config

    from alembic import command

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    # env.py reads this. Without it, fileConfig() would disable every logger
    # the application already configured, and the next error would vanish.
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


async def run_migrations() -> dict[str, Any]:
    """Apply migrations to head, once across the fleet."""
    if not ALEMBIC_INI.is_file():
        log.warning(
            "alembic.ini not found; skipping startup migrations",
            extra={"event": "bootstrap.migrations_skipped", "path": str(ALEMBIC_INI)},
        )
        return {"status": "skipped", "reason": "alembic.ini not found"}

    log.info("applying migrations", extra={"event": "bootstrap.migrations_start"})
    async with _AdvisoryLock(MIGRATION_LOCK_KEY):
        await asyncio.to_thread(_upgrade_sync)
    log.info("migrations at head", extra={"event": "bootstrap.migrations_done"})
    return {"status": "ok"}


async def run_seed() -> dict[str, Any]:
    """Insert whatever the database is missing. Writes nothing if it is complete."""
    from app.db.seed import seed_if_absent

    async with _AdvisoryLock(SEED_LOCK_KEY), session_scope() as session:
        outcome = await seed_if_absent(session)

    if outcome["status"] == "already_seeded":
        log.info("database already seeded", extra={"event": "bootstrap.seed_skipped"})
    else:
        log.info(
            "seeded missing data",
            extra={"event": "bootstrap.seed_done", "seeded": outcome["seeded"]},
        )
    return outcome


async def bootstrap() -> dict[str, Any]:
    """Whatever the environment asked for, in the only order that works.

    Migrations first: seeding writes to tables that may not exist yet. Failures
    are fatal rather than logged and swallowed - a service that silently starts
    against an un-migrated database fails later, in a way that is much harder
    to read than a refusal to boot.
    """
    report: dict[str, Any] = {"migrations": None, "seed": None}

    if settings.run_migrations_on_startup:
        report["migrations"] = await run_migrations()

    if settings.seed_on_startup:
        if settings.seeding_permitted:
            report["seed"] = await run_seed()
        else:
            # Not an error. The operator set a development convenience in a
            # deployed environment; say so clearly and carry on serving.
            log.warning(
                "SEED_ON_STARTUP is set but refused outside development",
                extra={
                    "event": "bootstrap.seed_refused",
                    "environment": settings.environment,
                },
            )
            report["seed"] = {"status": "refused", "reason": settings.environment}

    return report


__all__ = ["bootstrap", "run_migrations", "run_seed"]
