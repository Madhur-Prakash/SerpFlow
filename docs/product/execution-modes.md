# Execution modes

<p>
  <a href="../README.md#product"><img alt="docs: Product" src="https://img.shields.io/badge/docs-Product-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="modes: live · record · replay" src="https://img.shields.io/badge/modes-live%20%C2%B7%20record%20%C2%B7%20replay-2F6BFF">
  <img alt="test keys: always mock" src="https://img.shields.io/badge/test%20keys-always%20mock-3fcf8e">
  <img alt="SerpApi: 54 engines" src="https://img.shields.io/badge/SerpApi-54%20engines-2F6BFF">
  <a href="../../backend/app/services/runs.py"><img alt="source: services/runs.py" src="https://img.shields.io/badge/source-services%2Fruns.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Product](../README.md#product) › **Execution modes** · page 3 of 50

An execution mode answers one question: **where does this result come from, and does it cost anything?**

- **It used to be** a server-wide environment variable: every project in every organization on an instance executed the same way
- **It is now chosen where the decision belongs:** by the project, or by a single search
- The environment variable survives as the **floor**

**On this page:** [the four modes](#the-four-modes) · [who chooses, and precedence](#who-chooses-and-precedence) · [permission](#permission) · [setting it](#setting-it) · [why `mock` is not selectable](#why-mock-is-not-selectable)

## The four modes

| Mode | Reaches the network | Spends credits | Use it for |
|---|---|---|---|
| `live` | yes | **yes** | normal execution |
| `record` | yes | **yes** | live execution that also writes cassettes |
| `replay` | **never** | no | serving recorded cassettes; **the default** |
| `mock` | never | no | the deterministic generator; not selectable, see below |

- **`replay` is the default everywhere**, because it cannot spend money or touch the network by accident
- That is why `make dev` and `make seed` work with **no keys at all**
- **In `replay`, a cassette miss fails loudly**
  - it never quietly falls through to a live call: that would make "this run cost nothing" untrue
  - no configuration turns the fallthrough on

## Who chooses, and precedence

Most specific wins:

```
1.  API key environment is `test`   ─────►  mock      ABSOLUTE
2.  per-request  `mode` on /v1/search or /v1/plan
3.  the project's own execution mode
4.  SERPFLOW_MODE                            (instance default)
```

- **Rule 1 is checked first**, and nothing below it is consulted
  - a `test` key **always** routes to the deterministic mock and **always** costs zero
  - no setting at any level overrides that. It is the one guarantee the whole mode system exists to protect
- **Rules 2-4 resolve in one function**, [`resolve_execution_mode`](../../backend/app/services/runs.py)
  - so the precedence cannot drift between the planning, execution and streaming paths
- **An unrecognised mode resolves to `replay`, not `live`**
  - before modes were selectable, the final branch was only reachable with a validated setting, so defaulting to live was safe
  - now it is reachable with whatever a caller sent, and defaulting an unknown string to billable execution is the wrong way to be wrong

## Permission

| Choice | Needs | Why |
| --- | --- | --- |
| `replay` per request | nothing | choosing not to spend money is not a privilege |
| `live` or `record` per request | **`run:mode_override`** | held by developer, admin and owner; **not** analyst, **not** service keys |
| the project's default mode | `project:write` | an ordinary, reviewable configuration change |

- **A service key runs whatever its project is set to:** the auditable default
- **A caller without the permission who asks for live is refused**, not silently downgraded
  - executing against cassettes when someone asked for live data would make the result lie about its own provenance
- **The project setting is the right place** for a team to make the decision once

## Setting it

**Per project**, in the console under Settings → Projects, or:

```bash
curl -X PATCH https://your-instance/v1/projects/$PROJECT_ID \
  -H "Authorization: Bearer $SERPFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"execution_mode": "live"}'
```

- **Send `""` to clear it** and return the project to the instance default
  - a plain `null` cannot say that: in a PATCH, `null` means "leave this field alone"
- **A project with no mode of its own inherits `SERPFLOW_MODE`**, rather than being pinned to whatever it was at creation
  - changing the instance default later moves every project that never expressed a preference, and none that did

**Per request:**

```bash
curl -X POST https://your-instance/v1/search \
  -H "Authorization: Bearer $SERPFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"intent": "cafes in Koramangala", "mode": "live"}'
```

**Per instance**, in `.env`:

```bash
SERPFLOW_MODE=replay
```

- **The resolved mode, and why it resolved that way, travel with every response:**
  - on the run, and on each step
  - in the `X-SerpFlow-Mode` header
  - verbatim in the console
- Replayed or mocked data is **never** presented as live

## Why `mock` is not selectable

- `mock` is rule 1's answer and **nothing else's**
- It cannot be set on a project, in a request, or in `SERPFLOW_MODE`
- **If it were selectable**, "this run used the mock and cost nothing" would be a claim anyone could make about any run by setting a parameter
- **Because only a `test` API key reaches it**, it means something verifiable instead: a test key was used
- **The database enforces it too:** the `projects.execution_mode` check constraint admits only `live`, `record` and `replay`

## Related

- [ADR 0010: test key mode precedence](../adr/0010-test-key-mode-precedence.md)
- [Bring your own key](../security/byok.md)
- [API keys](../security/api-keys.md)
- [Demo](demo.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The reference demo](../product/demo.md) | [Docs index](../README.md) | [Routing benchmark](../product/benchmark.md) |
