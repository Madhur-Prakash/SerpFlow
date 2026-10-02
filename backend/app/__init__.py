"""SerpFlow - a search control plane for SerpApi.

The central thesis: SerpFlow does not merely cache search results. It re-plans
execution based on what is already warm, optimizing marginal cost rather than
cold cost.
"""

from __future__ import annotations

import asyncio
import contextlib
import selectors
import sys

__version__ = "0.1.0"

# psycopg's async driver cannot run on the Windows ProactorEventLoop, which is
# the platform default. Selecting the selector policy here - before any event
# loop is created - makes `make dev`, Alembic and the test suite behave
# identically on Windows and Linux. On other platforms this is a no-op.
if sys.platform == "win32":  # pragma: no cover - platform specific
    with contextlib.suppress(AttributeError):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    _ = selectors

__all__ = ["__version__"]
