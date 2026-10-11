# Execution modes

<p>
  <a href="../product/README.md"><img alt="docs: Product" src="https://img.shields.io/badge/docs-Product-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="modes: live · record · replay" src="https://img.shields.io/badge/modes-live%20%C2%B7%20record%20%C2%B7%20replay-2F6BFF">
  <img alt="test keys: always mock" src="https://img.shields.io/badge/test%20keys-always%20mock-3fcf8e">
  <img alt="SerpApi: 54 engines" src="https://img.shields.io/badge/SerpApi-54%20engines-2F6BFF">
  <a href="../../backend/app/core/config.py"><img alt="source: core/config.py" src="https://img.shields.io/badge/source-core%2Fconfig.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [Product](../product/README.md) › **Execution modes** · page 4 of 50

An execution mode answers one question: **where does this result come from, and does it cost anything?**

- **It used to be** a server-wide environment variable: every project in every organization on an instance executed the same way
- **It is now chosen where the decision belongs:** by the project, or by a single search. The project column arrived in migration [`0004_project_mode`](../database/migrations.md#0004_project_mode)
- The environment variable, [`SERPFLOW_MODE`](../security/secrets.md#inventory), survives as the **floor**

**On this page:** [the four modes](#the-four-modes) · [who chooses, and precedence](#who-chooses-and-precedence) · [permission](#permission) · [setting it](#setting-it) · [why `mock` is not selectable](#why-mock-is-not-selectable)

## The four modes

| Mode | Reaches the network | Spends credits | Use it for |
|---|---|---|---|
| `live` | yes | **yes** | normal execution |
| `record` | yes | **yes** | live execution that also writes cassettes |
| `replay` | **never** | no | serving recorded cassettes; **the default** |
| `mock` | never | no | the deterministic generator; not selectable, see below |

- **`replay` is the default everywhere** ([`app/core/config.py`](../../backend/app/core/config.py)), because it cannot spend money or touch the network by accident
- That is why [`make dev` and `make seed`](../deployment/local.md#everyday-targets) work with **no keys at all**
- **Cassettes** are recorded SerpApi responses, one JSON file per engine and request under `fixtures/cassettes`, written in `record` and read in `replay` by the SerpApi gateway the [executor](../architecture/executor.md) calls ([`cassettes.py`](../../backend/app/integrations/serpapi/cassettes.py)). None are committed
- **The `mock` generator** builds a deterministic payload per engine and request ([`app/integrations/serpapi/mock.py`](../../backend/app/integrations/serpapi/mock.py))
- **In `replay`, a cassette miss fails loudly**
  - it raises [`REPLAY_CASSETTE_MISS`](../operations/troubleshooting.md#replay_cassette_miss) (503), naming the cassette file it expected
  - it never quietly falls through to a live call: that would make "this run cost nothing" untrue
  - no configuration turns the fallthrough on
- **The mode only decides what serves a cache miss**
  - every step is looked up in the cache first, in every mode ([`app/services/executor/service.py`](../../backend/app/services/executor/service.py)), so a `replay` instance still answers an intent the cache already holds
  - the [Searches Archive](../architecture/caching.md#the-searches-archive) is tried only in `live` and `record`: reading it is an upstream call

## Who chooses, and precedence

Most specific wins:

```
1.  API key environment is `test`   ─────►  mock      ABSOLUTE
2.  per-request  `mode` on /v1/search or /v1/plan
3.  the project's own execution mode
4.  SERPFLOW_MODE                            (instance default)
```

- **Rule 1 is checked first**, and nothing below it is consulted ([ADR 0005](../adr/0005-test-key-mode-precedence.md))
  - a [`test` key](../security/api-keys.md#test-keys) **always** routes to the deterministic mock and **always** costs zero
  - no setting at any level overrides that. It is the one guarantee the whole mode system exists to protect
  - [`resolve_mode`](../../backend/app/integrations/serpapi/__init__.py) applies it, and states the reason on the result
- **Rules 2-4 resolve in one function**, [`resolve_execution_mode`](../../backend/app/services/runs.py)
  - so the precedence cannot drift between the planning, execution, streaming and run-replay paths
- **Only the REST API takes a per-request mode:** [`POST /v1/search`](../api/overview.md#plan-and-execute), its `/v1/run` alias, and [`POST /v1/plan`](../api/overview.md#plan-without-executing)
  - the console search, the [SDKs, the CLI and the MCP server](../sdks/overview.md) send none, so they always run on rule 3 or 4 (or rule 1, on a test key)
  - re-running a past run with [`POST /v1/runs/{id}/replay`](../api/overview.md#runs), which is unrelated to `replay` mode, resolves the mode afresh from the project, not from the original request
- **An unrecognised mode resolves to `replay`, not `live`**
  - before modes were selectable, the final branch was only reachable with a validated setting, so defaulting to live was safe
  - now it is reachable with whatever a caller sent, and defaulting an unknown string to billable execution is the wrong way to be wrong
  - **it is the backstop, not the front line:** a request asking for `mock` or anything unknown is refused with `422 VALIDATION_ERROR` by the request schema ([`app/schemas/planning.py`](../../backend/app/schemas/planning.py)), the project column has a check constraint, and `SERPFLOW_MODE` is typed, so a bad value stops the server at startup

## Permission

| Choice | Needs | Why |
| --- | --- | --- |
| `replay` per request | nothing | choosing not to spend money is not a privilege |
| `live` or `record` per request | **`run:mode_override`** | held by developer, admin and owner; **not** analyst, **not** service keys; grantable to a [custom role](../security/api-keys.md#custom-roles) |
| the project's default mode | `project:write` | an ordinary, reviewable configuration change |

- Roles and their permissions: [roles](../security/api-keys.md#roles), defined in [`app/core/permissions.py`](../../backend/app/core/permissions.py)
- **A service key runs whatever its project is set to:** the auditable default
- **A caller without the permission who asks for live is refused** with `403 PERMISSION_DENIED`, not silently downgraded ([errors](../api/overview.md#errors))
  - executing against cassettes when someone asked for live data would make the result lie about its own provenance
  - **the request is checked before rule 1 runs:** a `test` key without the permission is refused too, while one that holds it still gets the mock
- **The project setting is the right place** for a team to make the decision once

## Setting it

**Per project**, in the console under Settings → Projects, or with [`PATCH /v1/projects/{id}`](../api/overview.md#identity-and-access):

```bash
curl -X PATCH https://your-instance/v1/projects/$PROJECT_ID \
  -H "Authorization: Bearer $SERPFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"execution_mode": "live"}'
```

- **Send `""` to clear it** and return the project to the instance default ([`app/api/v1/organizations.py`](../../backend/app/api/v1/organizations.py))
  - a plain `null` cannot say that: in a PATCH, `null` means "leave this field alone"
- **The change is audited** as `project.updated`, with the before and after values
- **A project with no mode of its own inherits `SERPFLOW_MODE`**, rather than being pinned to whatever it was at creation
  - the column is `NULL` for "inherit" ([`0004_project_execution_mode.py`](../../backend/alembic/versions/0004_project_execution_mode.py))
  - changing the instance default later moves every project that never expressed a preference, and none that did

**Per request:**

```bash
curl -X POST https://your-instance/v1/search \
  -H "Authorization: Bearer $SERPFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"intent": "cafes in Koramangala", "mode": "live"}'
```

**Per instance**, in `.env` ([modes locally](../deployment/local.md#modes)):

```bash
SERPFLOW_MODE=replay
```

- **The resolved mode, and why it resolved that way, travel with every response:**
  - on the run, and on each step ([per-step record](../architecture/executor.md#per-step-record))
  - in the [`X-SerpFlow-Mode` header](../api/overview.md#provenance-headers)
  - verbatim in the console, as the mode badge and its reason
- A run and each of its steps record the mode they ran in, and `X-SerpFlow-Mode` returns it
- **Known gap:** the cache does not key on mode, so a payload first fetched by a mock or replay run can serve a later `live` run in the same partition as a cache hit ([caching: execution mode is not part of the key](../architecture/caching.md#execution-mode-is-not-part-of-the-key), [replay or mock data mistaken for live](../security/threat-model.md#replay-or-mock-data-mistaken-for-live))

## Why `mock` is not selectable

- `mock` is rule 1's answer and **nothing else's**
- It cannot be set on a project, in a request, or in `SERPFLOW_MODE`
- **If it were selectable**, "this run used the mock and cost nothing" would be a claim anyone could make about any run by setting a parameter
- **Because only a `test` API key reaches it**, it means something verifiable instead: a test key was used
- **The database enforces it too:** the `ck_projects_execution_mode` check constraint on [`projects`](../database/schema.md#identity)`.execution_mode` admits only `NULL`, `live`, `record` and `replay` ([migration 0004](../database/migrations.md#0004_project_mode))

## Related

- [ADR 0005](../adr/0005-test-key-mode-precedence.md): why a test key overrides every other setting, and the per-project update
- [API keys](../security/api-keys.md#test-keys): what a test key is and how one is minted
- [Bring your own key](../security/byok.md): the SerpApi credential `live` and `record` need
- [The executor](../architecture/executor.md): the gateway that reads and writes cassettes, and the credential boundary
- [Local development](../deployment/local.md#modes): switching modes on a dev machine
- [Troubleshooting](../operations/troubleshooting.md#replay_cassette_miss): what to do about `REPLAY_CASSETTE_MISS`
- [The reference demo](demo.md): every phase on a test key, so zero credits
- [Migrations](../database/migrations.md#0004_project_mode): the revision that made the mode per project
- [Product overview](product-overview.md): where modes fit in the product

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The reference demo](../product/demo.md) | [Docs index](../README.md) · [Product index](../product/README.md) | [Routing benchmark](../product/benchmark.md) |
