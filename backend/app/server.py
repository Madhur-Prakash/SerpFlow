"""Server entry point.

    python -m app.server
    python -m app.server --reload --port 8001

Why this exists rather than calling ``uvicorn app.main:app`` directly:

uvicorn picks its event loop with a factory, not the asyncio policy, and on
Windows that factory returns ``ProactorEventLoop`` for a single-process run.
psycopg's async driver cannot run on a proactor loop, so every database call
would fail with an InterfaceError - while the same code works under pytest and
under Docker, which makes it a genuinely confusing first-run experience.

This module drives uvicorn with an explicit ``SelectorEventLoop`` factory so a
single-process run behaves identically on Windows, Linux and in a container.
The reload path already spawns subprocesses, for which uvicorn selects the
selector loop itself, so that path is handed back to uvicorn unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SerpFlow API.")
    # Containers and `make dev` both need the service reachable from outside
    # the process namespace; a deployment binds its own interface upstream.
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    import uvicorn

    common = {
        "host": args.host,
        "port": args.port,
        "log_level": args.log_level,
        "proxy_headers": True,
        "forwarded_allow_ips": "*",
        "access_log": False,
    }

    if args.reload or args.workers > 1:
        # The supervisor path. uvicorn spawns workers and already selects a
        # selector loop for them.
        uvicorn.run(
            "app.main:app",
            reload=args.reload,
            workers=None if args.reload else args.workers,
            **common,
        )
        return 0

    config = uvicorn.Config("app.main:app", **common)
    server = uvicorn.Server(config)
    asyncio.run(server.serve(), loop_factory=_loop_factory())
    return 0


def _loop_factory():
    """A selector loop on every platform.

    ``asyncio.SelectorEventLoop`` exists on Windows too, where it is the
    non-default alternative to the proactor loop. On Linux and macOS it is
    already the default, so this is a no-op there.
    """
    if sys.platform == "win32":  # pragma: no cover - platform specific
        return asyncio.SelectorEventLoop
    return asyncio.new_event_loop


if __name__ == "__main__":
    raise SystemExit(main())
