# 0005. A test key overrides the execution mode, absolutely

<p>
  <a href="../adr/README.md"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/tests/unit/test_security.py"><img alt="source: unit/test_security.py" src="https://img.shields.io/badge/source-unit%2Ftest__security.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../adr/README.md) › **0005. A test key overrides the execution mode, absolutely** · page 61 of 65

**Status** Accepted

## Context

**Four [execution modes](../product/execution-modes.md#the-four-modes)**, interacting with the credential the caller presents:

```
live     normal billable execution against SerpApi
record   execute live and persist cassettes
replay   serve from cassettes, never the network
mock     deterministic generated results
```

- **Two inputs, one outcome:** [`SERPFLOW_MODE`](../deployment/local.md#modes) is an environment variable; API keys carry an [environment segment](../security/api-keys.md#format), `sf_live_...` or `sf_test_...`. Which wins?
- **Getting this wrong costs money in the most embarrassing way available:** a test suite that spends real credits because `SERPFLOW_MODE` happened to be `live` in that shell

## Decision

**A `test` API key routes to the deterministic mock regardless of `SERPFLOW_MODE`.** The precedence is absolute, and no configuration overrides it.

```python
# app/core/security.py: ParsedApiKey
@property
def is_test(self) -> bool:
    return self.environment == "test"
```

- **The environment segment is readable from the key structure before any database lookup**, so the decision is made at the earliest possible point, not deep in the executor where a code path might miss it
  - asserted by `test_test_keys_are_identifiable_before_any_database_lookup` in [`test_security.py`](../../backend/tests/unit/test_security.py)
- **Rule 1 is the first branch of [`resolve_mode`](../../backend/app/integrations/serpapi/__init__.py)**, and returns before any configured mode is read
- **The corollary, equally absolute: replay never silently accesses the network**
  - a cassette miss raises [`REPLAY_CASSETTE_MISS`](../operations/troubleshooting.md#replay_cassette_miss) and fails the request
  - it does **not** fall back to a live call
- **Every response carries [`X-SerpFlow-Mode`](../api/overview.md#provenance-headers)**, always present, so mocked or replayed data is never presented as live

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

- **The mode later became selectable per project, and per request** (migration [`0004_project_mode`](../database/migrations.md#0004_project_mode)), resolved most-specific-first: test key → request → project → `SERPFLOW_MODE`
- **This decision still holds unchanged:** rule 1, the test key, is checked first and nothing below it can override it
- **The rejected concern was addressed with permissions:** choosing `live` or `record` per request needs [`run:mode_override`](../product/execution-modes.md#permission), which analysts and service keys do not hold, and a caller without it is refused rather than downgraded
- **`mock` remains unselectable:** only a `test` key reaches it. Details: [execution modes](../product/execution-modes.md)
- **Update (2026-10-11): where a refusal comes first, and what the header reports**
  - **A per-request mode is validated and permission-checked before rule 1 runs** ([`resolve_execution_mode`](../../backend/app/services/runs.py)): a test key asking for `live` without `run:mode_override` is refused, and with it is mocked. Either way it never spends
  - **`X-SerpFlow-Mode` carries the resolved mode on `/v1/plan`, `/v1/search` and `/v1/run`.** Every other route, including the `202` that starts a streamed search, reports `MOCK` for a test key and `SERPFLOW_MODE` otherwise ([`middleware.py`](../../backend/app/api/middleware.py)); the response body's `mode` and the run record carry the resolved one

## Related

- [Execution modes: who chooses, and precedence](../product/execution-modes.md#who-chooses-and-precedence): the four rules, the permission table and how to set each level
- [API keys: test keys](../security/api-keys.md#test-keys): what an `sf_test_` key does, and that budgets still apply to it
- [Local development: modes](../deployment/local.md#modes): `SERPFLOW_MODE` locally, and why a live key in `.env` is safe to develop against
- [Executor: the credential boundary](../architecture/executor.md#the-credential-boundary): only `live` and `record` resolve and decrypt a credential
- [`test_execution_modes.py`](../../backend/tests/unit/test_execution_modes.py): a test key cannot be talked into spending, an unknown mode falls back to replay, `mock` cannot be configured
- [Threat model: replay or mock data mistaken for live](../security/threat-model.md#replay-or-mock-data-mistaken-for-live): the threat the mode header and run record answer
- [Troubleshooting: `REPLAY_CASSETTE_MISS`](../operations/troubleshooting.md#replay_cassette_miss): the loud failure chosen over a quiet charge

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0009: Available is not acceptable: freshness g…](../adr/0009-freshness-gates-warmth.md) | [Docs index](../README.md) · [Architecture decision records](../adr/README.md) | [ADR 0006: Tenant isolation enforced twice](../adr/0006-rls-plus-application-guards.md) |
