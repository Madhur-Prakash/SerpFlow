# 0010. A test key overrides the execution mode, absolutely

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0010. A test key overrides the execution mode, absolutely** · page 46 of 50

**Status** Accepted

## Context

**Four execution modes**, interacting with the credential the caller presents:

```
live     normal billable execution against SerpApi
record   execute live and persist cassettes
replay   serve from cassettes, never the network
mock     deterministic generated results
```

- **Two inputs, one outcome:** `SERPFLOW_MODE` is an environment variable; API keys carry an environment segment, `sf_live_...` or `sf_test_...`. Which wins?
- **Getting this wrong costs money in the most embarrassing way available:** a test suite that spends real credits because `SERPFLOW_MODE` happened to be `live` in that shell

## Decision

**A `test` API key routes to the deterministic mock regardless of `SERPFLOW_MODE`.** The precedence is absolute, and no configuration overrides it.

```python
@property
def is_test(self) -> bool:
    return self.environment == "test"
```

- **The environment segment is readable from the key structure before any database lookup**, so the decision is made at the earliest possible point, not deep in the executor where a code path might miss it
- **The corollary, equally absolute: replay never silently accesses the network**
  - a cassette miss raises `REPLAY_CASSETTE_MISS` and fails the request
  - it does **not** fall back to a live call
- **Every response carries `X-SerpFlow-Mode`**, always present, so mocked or replayed data is never presented as live

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **`SERPFLOW_MODE` wins** | A developer with a live-configured environment cannot safely run tests, and the failure is silent **and billable** |
| **A per-request mode parameter as the deciding input** | Another input to get wrong, moving the decision to the caller, including a compromised one. (See the update below: it was later added **beneath** rule 1, never above it) |
| **Replay falls back to live on a miss** | Superficially convenient: the test passes instead of failing. The worst option on the list: replay's whole point is a guarantee of no network access, and a fallback turns that guarantee into a hope. A missing cassette should be **loud** |

## Cost

- **A `live` key is required to spend real credits**
  - a developer deliberately testing live behaviour has to use the right key, not flip an environment variable
  - that friction is intentional
- **`REPLAY_CASSETTE_MISS` will be hit regularly during development**
  - a real error that stops work until a cassette is recorded or a `test` key is used
  - the alternative is a quiet charge, which is worse

## Update: per-project and per-request modes

- **The mode later became selectable per project, and per request** (migration `0004_project_mode`), resolved most-specific-first: test key → request → project → `SERPFLOW_MODE`
- **This decision still holds unchanged:** rule 1, the test key, is checked first and nothing below it can override it
- **The rejected concern was addressed with permissions:** choosing `live` or `record` per request needs `run:mode_override`, which analysts and service keys do not hold, and a caller without it is refused rather than downgraded
- **`mock` remains unselectable:** only a `test` key reaches it. Details: [execution modes](../product/execution-modes.md)

## See also

- [Execution modes](../product/execution-modes.md)
- [API keys](../security/api-keys.md)
- [Local development](../deployment/local.md)
- [Executor architecture](../architecture/executor.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0009: Available is not acceptable: freshness g…](../adr/0009-freshness-gates-warmth.md) | [Docs index](../README.md) | [ADR 0011: Tenant isolation enforced twice](../adr/0011-rls-plus-application-guards.md) |
