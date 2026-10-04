# Contributing to SerpFlow

Thanks for considering it. This document covers how to get the project
running, what the tests expect, and the two or three places where the codebase
has opinions worth knowing before you change them.

## Getting set up

```bash
cp .env.example .env
make install        # uv venv on Python 3.13, plus npm install
make up             # postgres with pgvector, redis, kafka in KRaft mode
make upgrade        # alembic migrations
make seed           # catalog, benchmark fixtures, demo organization
make test           # 115 tests
```

No API keys are required. Planning uses a deterministic adapter and
`test` API keys route to a deterministic SerpApi mock, so the whole project
works offline.

## Before you open a pull request

```bash
make format         # ruff format + fix, prettier
make lint           # ruff check, eslint
make typecheck      # mypy, tsc
make test           # unit, integration and e2e
make demo           # the thesis must still hold
```

`make demo` exits non-zero if cache-aware replanning stops changing the
selected plan. That is not a style check: it is the product.

## Where things live

| You want to change | Look in |
| --- | --- |
| What an engine can do, or what it chains to | `backend/app/services/catalog/data/v1/*.yaml` |
| How chains are computed | `backend/app/services/catalog/graph.py` |
| How candidates are generated and ranked | `backend/app/services/planner/` |
| Cache layers, the entity guard, TTL | `backend/app/services/cache/` |
| Execution order and credential handling | `backend/app/services/executor/` |
| Endpoints | `backend/app/api/v1/` |
| The control-plane UI | `frontend/src/pages/` |

## Changing the catalog

The catalog is the single largest body of domain knowledge here, and it has a
defined authoring method. `make catalog-build` regenerates *drafts* from the
SerpApi documentation into `data/_drafts/`. It never writes a committed file,
because two of the six steps cannot be automated:

- **Dependency edges.** A scraper can see that `google_maps_reviews` takes a
  `data_id`. Only a person decides that
  `google_maps.local_results[].data_id` is the field that satisfies it.
- **Capability tags and substitutes.** Grouping engines by what they actually
  compete on, and writing down the real trade-off, is judgement work.

When you add a substitute, the `note` is user-facing copy: it appears verbatim
in Plan Inspector rejection reasons. "Different coverage" is not a note.
"Sparse coverage outside US metros, and the reviewer identity shape differs, so
contributor-history chaining is not available downstream" is.

Run `make catalog-validate` after any catalog change. Every engine must either
declare substitutes or state in `single_source_note` why nothing competes with
it, so the planner can explain the absence rather than being silent about it.

## Changing the planner

Two invariants the tests enforce:

1. **Stage D emits multiple candidates wherever alternatives exist.** A
   single-candidate result is valid only when no alternative path exists, and
   the Plan must record `single_candidate_reason` saying why. If stage D
   routinely returns one plan, marginal replanning has nothing to re-rank.

2. **Available is not acceptable.** A warm cache entry counts toward marginal
   savings only if it also satisfies the step's freshness requirement. If you
   relax that, the planner will cheerfully serve a month-old price as a current
   one.

Coverage is ranked before price. A narrow-coverage substitute being cheaper is
not a reason to answer a different question; cost only breaks ties within a
coverage band.

## Changing the cache

The entity and numeral guard is deliberately not a model call. It extracts
numerals, version identifiers and named entities from both queries and requires
exact set equality, and it does not look at the similarity score at all. A
model that is right 95% of the time still serves Indiranagar results for a
Koramangala query once every twenty requests, and nobody reports that bug.

If you change the guard, `tests/unit/test_cache_guard.py` asserts the two cases
the design exists for: `iphone 16` never matches `iphone 17`, and
`restaurants in Koramangala` never matches `restaurants in Indiranagar`.

## Secrets

Three rules, all of them tested:

- The upstream SerpApi credential is decrypted in exactly one place, the
  executor. If you find yourself decrypting it in an API handler, something has
  gone wrong upstream of that line.
- No response schema may contain a field that could carry it. Not excluded -
  absent. `tests/unit/test_security.py` walks every Pydantic model in
  `app/schemas` and fails if one appears.
- The redaction filter runs on the log record, the formatted message and the
  exception path. The leak path is always an exception handler.

## Database changes

All schema changes go through Alembic.

```bash
make migration ARGS="-m 'add thing'"
make upgrade
make downgrade      # confirm it reverses cleanly
```

Every tenant-scoped table needs `org_id`, an index on it, and an entry in
`RLS_TABLES` in the initial migration so row-level security covers it. The
application guards in `app/api/deps.py` are the primary check; RLS is the
backstop for the query somebody forgets to scope.

## Tests

| Suite | Needs | Covers |
| --- | --- | --- |
| `tests/unit` | nothing | catalog, path-finding, candidates, cost, freshness, guard, keys, credentials, RBAC, TTL, redaction |
| `tests/integration` | postgres, redis | the real app over HTTP, SSE frames, provenance headers, audit chain |
| `tests/e2e` | postgres, redis | the thesis assertion, single-candidate reasoning, locale inference |

Integration and e2e tests skip themselves cleanly when PostgreSQL is not
reachable, so `make test` is useful on a laptop with nothing running.

The benchmark is **not** part of CI. It makes real LLM calls and is run on
demand with `make benchmark`; results commit per catalog version under
`backend/fixtures/benchmark/results/`.

## Style

- Python: ruff, 100 columns, type hints on public functions.
- TypeScript: strict mode, no `any` in exported types.
- Comments explain *why*, especially where the obvious implementation is
  wrong. There are several places here where the straightforward version
  silently produces a worse product; those are commented.
- No emojis anywhere, including commit messages, documentation and UI copy.
  Icons are Lucide, and never decorative sparkle or star glyphs.

## Reporting a security issue

Please do not open a public issue. See [SECURITY.md](SECURITY.md).
