# 0013. Run uvicorn through an explicit loop factory

**Status** Accepted

## Context

psycopg's async driver cannot run on Windows' `ProactorEventLoop`. Every
database call fails with an `InterfaceError`.

The standard fix is the event loop policy, set at import:

```python
# app/__init__.py
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

That was not enough. uvicorn 0.54 does not consult the policy for a
single-process run — it selects its loop through its own
`asyncio_loop_factory`, which returns `ProactorEventLoop` on Windows.

The resulting failure is unusually confusing: the same code works under pytest,
works in Docker, and works with `--reload`, and fails only on a plain
`uvicorn app.main:app` on Windows. Three of the four paths suggest the code is
fine.

## Decision

A dedicated entry point that drives uvicorn with an explicit loop factory.

```python
# app/server.py
config = uvicorn.Config("app.main:app", **common)
server = uvicorn.Server(config)
asyncio.run(server.serve(), loop_factory=_loop_factory())
```

```python
def _loop_factory():
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop
    return asyncio.new_event_loop
```

`SelectorEventLoop` exists on Windows as the non-default alternative; on Linux
and macOS it is already the default, so this is a no-op there and the behaviour
is identical across all three.

The `--reload` and `--workers` paths are handed back to `uvicorn.run()`
unchanged, because uvicorn spawns subprocesses there and already selects a
selector loop for them.

`make backend` and the container both run `python -m app.server`. The policy in
`app/__init__.py` stays as well — it covers scripts, the CLI and the test
suite, which do not go through this entry point.

## Alternatives rejected

**Policy only.** Does not work, as above. The policy is what everyone tries
first and is why this ADR exists.

**Use asyncpg instead of psycopg.** Avoids the issue, and psycopg 3 is the
better driver for this workload — notably for `SET LOCAL` handling under
pooling, which the RLS implementation depends on. Changing drivers to work
around a loop selection detail is the wrong direction.

**Document "use WSL on Windows".** The stated goal is that `make dev` works on
a clean machine. Telling a Windows contributor their platform is unsupported is
a worse answer than fifteen lines in an entry point.

**Pin an older uvicorn.** Freezes a dependency over one behaviour, and the
behaviour is not a bug.

## Cost

One more module, and a documented rule that `uvicorn app.main:app` is not the
way to start the server. Both the Makefile and the Dockerfile use
`python -m app.server`, so the correct path is the default everywhere.

The argument parser in `app/server.py` has to mirror the uvicorn flags anyone
would reach for. It covers `--host`, `--port`, `--reload`, `--workers` and
`--log-level`, which is the set that matters.

## See also

- [Backend architecture](../architecture/backend.md)
- [Troubleshooting](../operations/troubleshooting.md)
