"""Startup bootstrap and the trusted-proxy address resolution.

The bootstrap's integration behaviour (it really migrates, it really seeds) is
covered in ``tests/integration``. What is asserted here is the part that is
pure policy: when it refuses, and what it decides without touching a database.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


# --------------------------------------------------------------------------
# Seed refusal (SEED_ON_STARTUP)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("environment", ["local", "dev"])
def test_seeding_is_permitted_in_development(environment):
    assert Settings(environment=environment).seeding_permitted is True


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_seeding_is_refused_outside_development(environment):
    """The seed creates demo accounts with a password committed to this repo."""
    assert Settings(environment=environment).seeding_permitted is False


@pytest.mark.asyncio
async def test_bootstrap_refuses_to_seed_in_production(monkeypatch):
    import app.db.bootstrap as bootstrap

    monkeypatch.setattr(bootstrap.settings, "run_migrations_on_startup", False)
    monkeypatch.setattr(bootstrap.settings, "seed_on_startup", True)
    monkeypatch.setattr(bootstrap.settings, "environment", "production")

    report = await bootstrap.bootstrap()

    assert report["seed"] == {"status": "refused", "reason": "production"}
    assert report["migrations"] is None


@pytest.mark.asyncio
async def test_bootstrap_does_nothing_when_both_flags_are_off(monkeypatch):
    """Default behaviour: an upgrade changes nothing for an existing deployment."""
    import app.db.bootstrap as bootstrap

    monkeypatch.setattr(bootstrap.settings, "run_migrations_on_startup", False)
    monkeypatch.setattr(bootstrap.settings, "seed_on_startup", False)

    assert await bootstrap.bootstrap() == {"migrations": None, "seed": None}


def test_both_flags_default_to_off(monkeypatch):
    """The code default, which is what applies when nothing sets them.

    `.env.example` ships them as true for convenience; the fallback stays
    false so upgrading a deployment that never set them changes nothing.
    """
    monkeypatch.delenv("RUN_MIGRATIONS_ON_STARTUP", raising=False)
    monkeypatch.delenv("SEED_ON_STARTUP", raising=False)
    settings = Settings(_env_file=None)
    assert settings.run_migrations_on_startup is False
    assert settings.seed_on_startup is False


def test_the_two_advisory_locks_are_distinct():
    """One process seeding must not block another from migrating, or vice versa."""
    import app.db.bootstrap as bootstrap

    assert bootstrap.MIGRATION_LOCK_KEY != bootstrap.SEED_LOCK_KEY


def test_alembic_ini_resolves_from_the_package():
    """The path has to be right inside the container as well as on a laptop."""
    import app.db.bootstrap as bootstrap

    assert bootstrap.ALEMBIC_INI.is_file()
    assert (bootstrap.PROJECT_ROOT / "alembic" / "env.py").is_file()


# --------------------------------------------------------------------------
# TRUSTED_PROXY_HOPS
# --------------------------------------------------------------------------
class _Request:
    def __init__(self, forwarded: str | None, peer: str = "10.0.0.9") -> None:
        self.headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
        self.client = type("Client", (), {"host": peer})()


@pytest.fixture
def hops(monkeypatch):
    def _set(value: int):
        import app.api.deps as deps

        monkeypatch.setattr(deps.settings, "trusted_proxy_hops", value)

    return _set


def test_a_spoofed_leftmost_entry_is_ignored(hops):
    """The attack this setting exists to stop.

    Taking the leftmost entry would let anyone set X-Forwarded-For and get a
    fresh rate-limit bucket on every request.
    """
    from app.api.deps import client_ip

    hops(1)
    assert client_ip(_Request("1.2.3.4, 203.0.113.7")) == "203.0.113.7"


def test_two_hops_reads_two_from_the_right(hops):
    from app.api.deps import client_ip

    hops(2)
    assert client_ip(_Request("1.2.3.4, 198.51.100.5, 203.0.113.7")) == "198.51.100.5"


def test_zero_hops_ignores_the_header_entirely(hops):
    """Exposed directly: the header is pure client input and worth nothing."""
    from app.api.deps import client_ip

    hops(0)
    assert client_ip(_Request("1.2.3.4, 203.0.113.7")) == "10.0.0.9"


def test_falls_back_to_the_peer_without_a_header(hops):
    from app.api.deps import client_ip

    hops(1)
    assert client_ip(_Request(None)) == "10.0.0.9"


def test_a_header_shorter_than_the_configured_hops_is_not_trusted(hops):
    """Fewer entries than hops means it did not traverse the proxies it should."""
    from app.api.deps import client_ip

    hops(2)
    assert client_ip(_Request("1.2.3.4")) == "10.0.0.9"


def test_whitespace_and_empty_entries_are_tolerated(hops):
    from app.api.deps import client_ip

    hops(1)
    assert client_ip(_Request("  1.2.3.4 ,  203.0.113.7  ")) == "203.0.113.7"


def test_default_matches_the_bundled_nginx():
    assert Settings().trusted_proxy_hops == 1
