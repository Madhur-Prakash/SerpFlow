# 0013. Run uvicorn through an explicit loop factory

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/__init__.py"><img alt="source: app/__init__.py" src="https://img.shields.io/badge/source-app%2F____init____.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0013. Run uvicorn through an explicit loop factory** · page 56 of 57

**Status** Accepted

## Context

- **psycopg's async driver cannot run on Windows' `ProactorEventLoop`.** Every database call fails with an `InterfaceError` ([async on Windows](../architecture/backend.md#async-on-windows))
- **The standard fix is the event loop policy**, set at import ([`app/__init__.py`](../../backend/app/__init__.py)):

```python
# app/__init__.py
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

- **That was not enough.** uvicorn 0.54 does not consult the policy for a single-process run: it selects its loop through its own `asyncio_loop_factory`, which returns `ProactorEventLoop` on Windows
- **The failure is unusually confusing:**

| Path | Result |
| --- | --- |
| pytest | works |
| Docker | works |
| `--reload` | works |
| plain `uvicorn app.main:app` on Windows | **fails** |

- Three of the four paths suggest the code is fine

## Decision

**A dedicated entry point that drives uvicorn with an explicit loop factory** ([`app/server.py`](../../backend/app/server.py)).

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

- **`SelectorEventLoop` exists on Windows** as the non-default alternative; on Linux and macOS it is already the default, so this is a no-op there, and behaviour is identical across all three
- **The `--reload` and `--workers` paths are handed back to `uvicorn.run()` unchanged:** uvicorn spawns subprocesses there and already picks a selector loop for them
- **[`make backend`](../deployment/local.md#everyday-targets) and the [container](../deployment/docker.md#the-backend-image) both run `python -m app.server`**
  - `make backend` passes `--reload`, so it takes the `uvicorn.run()` path; the container's `CMD` does not, so it takes the explicit factory
- **The policy in `app/__init__.py` stays too:** it covers scripts, the CLI and the test suite, which do not go through this entry point

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Policy only** | Does not work, as above. It is what everyone tries first, and why this ADR exists |
| **Use asyncpg instead of psycopg** | Avoids the issue, but psycopg 3 is the better driver for this workload, notably for `SET LOCAL` under pooling, which [RLS](../database/rls.md#how-it-works) depends on. Changing drivers to work around a loop-selection detail is the wrong direction |
| **Document "use WSL on Windows"** | The goal is that [`make dev`](../deployment/local.md#first-run) works on a clean machine. Telling a Windows contributor their platform is unsupported is worse than fifteen lines in an entry point |
| **Pin an older uvicorn** | Freezes a dependency over one behaviour, and the behaviour is not a bug |

## Cost

- **One more module**, and a documented rule: `uvicorn app.main:app` is not how to start the server
  - the Makefile and the Dockerfile both use `python -m app.server`, so the correct path is the default everywhere
- **`app/server.py`'s argument parser must mirror the uvicorn flags people reach for:** `--host`, `--port`, `--reload`, `--workers`, `--log-level`. That set is what matters

## See also

- [Backend: async on Windows](../architecture/backend.md#async-on-windows): the rule as the backend applies it, alongside the policy in `app/__init__.py`
- [Troubleshooting: psycopg fails on Windows](../operations/troubleshooting.md#psycopg-fails-on-windows-proactoreventloop): the `InterfaceError` this prevents, and what to check if it appears
- [Docker: the backend image](../deployment/docker.md#the-backend-image): the container `CMD` that starts `app.server`
- [Local development: everyday targets](../deployment/local.md#everyday-targets): `make backend` and `make dev`, both through the entry point
- [Installation: Windows](../deployment/installation.md#windows): the native Windows setup this decision keeps working
- [ADR 0011: tenant isolation enforced twice](0011-rls-plus-application-guards.md): the `SET LOCAL` under pooling that keeps the driver psycopg 3

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0012: The audit log is append-only in the data…](../adr/0012-append-only-audit-log.md) | [Docs index](../README.md) | [ADR 0014: Persist every candidate plan, not just t…](../adr/0014-persist-every-candidate.md) |
