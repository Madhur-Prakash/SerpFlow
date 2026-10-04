# Execution modes

An execution mode answers one question: **where does this result come from, and
does it cost anything?**

It used to be a server-wide environment variable, which meant every project in
every organization on an instance executed the same way. It is now chosen at
the level the decision actually belongs to — by the project, or by a single
search — with the environment variable surviving as the floor.

- [The four modes](#the-four-modes)
- [Who chooses, and precedence](#who-chooses-and-precedence)
- [Permission](#permission)
- [Setting it](#setting-it)
- [Why `mock` is not selectable](#why-mock-is-not-selectable)

## The four modes

| Mode | Reaches the network | Spends credits | Use it for |
|---|---|---|---|
| `live` | yes | **yes** | normal execution |
| `record` | yes | **yes** | live execution that also writes cassettes |
| `replay` | **never** | no | serving recorded cassettes; the default |
| `mock` | never | no | the deterministic generator — not selectable, see below |

`replay` is the default everywhere because it cannot spend your money or touch
the network by accident. `make dev` and `make seed` work with no keys at all
because of it.

In `replay`, a cassette miss **fails loudly**. It does not quietly fall through
to a live call — that would make "this run cost nothing" untrue, and there is
no configuration that turns the fallthrough on.

## Who chooses, and precedence

Most specific wins:

```
1.  API key environment is `test`   ─────►  mock      ABSOLUTE
2.  per-request  `mode` on /v1/search or /v1/plan
3.  the project's own execution mode
4.  SERPFLOW_MODE                            (instance default)
```

Rule 1 is checked first and nothing below it is consulted. A `test` key always
routes to the deterministic mock and always costs zero, and no setting at any
level overrides that. It is the one guarantee the whole mode system exists to
protect.

Rules 2–4 are resolved in a single function,
[`resolve_execution_mode`](../../backend/app/services/runs.py), so the
precedence cannot drift between the planning path, the execution path and the
streaming path.

An unrecognised mode resolves to `replay`, not to `live`. Before the mode was
selectable the final branch could only be reached by a validated setting, so
defaulting to live was safe; now it is reachable with whatever a caller sent,
and defaulting an unknown string to billable execution is the wrong way to be
wrong.

## Permission

Choosing `replay` needs nothing. Choosing not to spend money is not a
privilege, and any caller who can run a search can ask for it.

Choosing `live` or `record` per request needs **`run:mode_override`**, carried
by the developer, admin and owner roles — not by analyst, and not by service
keys. A service key runs whatever its project is set to, which is the
auditable default.

A caller without the permission who asks to go live is **refused**, not
silently downgraded. Executing against cassettes when someone asked for live
data would make the result a lie about its own provenance.

Setting the *project's* default mode is a separate, ordinary `project:write` —
it is a configuration change, reviewed like any other, and it is the right
place for a team to make the decision once.

## Setting it

**Per project**, in the console under Settings → Projects, or:

```bash
curl -X PATCH https://your-instance/v1/organizations/projects/$PROJECT_ID \
  -H "Authorization: Bearer $SERPFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"execution_mode": "live"}'
```

Send `""` to clear it and return the project to the instance default. A plain
`null` cannot express that — in a PATCH, `null` means "leave this field alone".

A project with no mode of its own **inherits** `SERPFLOW_MODE` rather than
being pinned to whatever it happened to be at creation. An operator who later
changes the instance default moves every project that never expressed a
preference, and moves none that did.

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

The resolved mode and the reason it was resolved travel with every response —
on the run, on each step, in the `X-SerpFlow-Mode` header, and verbatim in the
console. Replayed or mocked data is never presented as live.

## Why `mock` is not selectable

`mock` is rule 1's answer and nothing else's. It cannot be set on a project, in
a request, or in `SERPFLOW_MODE`.

If it were selectable, "this run used the deterministic mock and cost nothing"
would become a claim anyone could make about any run by setting a parameter.
Because it is reachable only through a `test` API key, it instead means
something verifiable: a test key was used. The constraint is enforced in the
database too — the `projects.execution_mode` check constraint admits only
`live`, `record` and `replay`.

---

**Related:** [ADR 0010 — test key mode precedence](../adr/0010-test-key-mode-precedence.md) ·
[bring your own key](../security/byok.md) ·
[api-keys.md](../security/api-keys.md) ·
[demo.md](demo.md)
