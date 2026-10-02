"""Seed a working SerpFlow instance.

    python scripts/seed.py            seed everything
    python scripts/seed.py --reset    delete the demo org first
    python scripts/seed.py --if-absent    seed only what is missing

Runs after migrations and needs no API keys of any kind (section 41). The
printed test key routes to the deterministic mock and spends zero SerpApi
credits, so the whole product is explorable before a paid account exists.

The implementation lives in ``app/db/seed.py`` so the application's startup
bootstrap can reuse it; this file is the command line around it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import setup_logging  # noqa: E402
from app.db.seed import DEMO_SESSION_CAP, seed_all, seed_if_absent  # noqa: E402
from app.db.session import session_scope  # noqa: E402


def _banner(result: dict, catalog: dict | None, tasks: int) -> None:
    line = "-" * 74
    print("")
    print(line)
    print("SerpFlow seed complete")
    print(line)
    if catalog is not None:
        print("Catalog version      " + catalog["catalog_version"])
        print(
            "Catalog contents     "
            + str(catalog["engines"])
            + " engines, "
            + str(catalog["edges"])
            + " dependency edges, "
            + str(catalog["substitutes"])
            + " substitute edges"
        )
    else:
        print("Catalog              already projected, left alone")
    print("Benchmark tasks      " + (str(tasks) + " loaded" if tasks else "already loaded"))
    print("")
    if result.get("status") == "exists":
        print("Demo organization already present (" + str(result.get("org_id", "")) + ").")
        print("Run with --reset to recreate it and print fresh keys.")
        print(line)
        return

    print("Sign in at http://localhost:5173")
    print("  owner    " + result["owner_email"] + "  /  " + result["password"])
    print("  analyst  " + result["analyst_email"] + "  /  " + result["password"])
    print("")
    print("API keys (shown once, exactly as the product shows them):")
    print("  test     " + result["keys"]["test"])
    print("           routes to the deterministic mock, spends 0 SerpApi credits")
    print("  live     " + result["keys"]["live"])
    print("           honours SERPFLOW_MODE; needs a real credential in the vault")
    print("  service  " + result["keys"]["service"])
    print("           MCP service principal, " + str(DEMO_SESSION_CAP) + "-credit session cap")
    print("  market   " + result["keys"]["market_test"])
    print("           second project, for the cross-project cache benefit view")
    print("")
    print("Next:")
    print("  make demo        run the reference demo and prove the thesis")
    print("  make dev         start the API and the frontend")
    print(line)
    print("")


async def main(reset: bool = False, if_absent: bool = False) -> int:
    setup_logging()
    async with session_scope() as session:
        if if_absent:
            outcome = await seed_if_absent(session)
        else:
            outcome = await seed_all(session, reset=reset)

    _banner(outcome["demo"], outcome["catalog"], outcome["tasks"])
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed SerpFlow.")
    parser.add_argument(
        "--reset", action="store_true", help="delete and recreate the demo organization"
    )
    parser.add_argument(
        "--if-absent",
        action="store_true",
        help="seed only what is missing; do nothing if the database is already seeded",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(reset=args.reset, if_absent=args.if_absent)))
