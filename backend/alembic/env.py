"""Alembic environment.

All schema changes go through Alembic (section 82). There is no manual schema
setup anywhere, and ``make seed`` runs after migrations.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings

# Importing the models package registers every table on the metadata, which is
# what autogenerate compares against.
from app.db.models import metadata as target_metadata  # noqa: F401

config = context.config

# `configure_logger` is set to False by the application's startup bootstrap.
# fileConfig() disables every existing logger by default, so running Alembic
# in-process would otherwise silence the application's own logging for the rest
# of the process - including whatever error came next.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", _url := settings.database_url)


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep autogenerate out of extension-owned objects."""
    return not (type_ == "table" and name in {"alembic_version", "spatial_ref_sys"})


def run_migrations_offline() -> None:
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url
    connectable = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
