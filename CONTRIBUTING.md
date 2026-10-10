# Contributing to SerpFlow

<p>
  <a href="#getting-set-up"><img alt="setup: no API keys" src="https://img.shields.io/badge/setup-no%20API%20keys-3fcf8e"></a>
  <a href="#tests"><img alt="tests: 216 passing" src="https://img.shields.io/badge/tests-216%20passing-3fcf8e?logo=pytest&logoColor=white"></a>
  <a href="#before-you-open-a-pull-request"><img alt="make demo: must stay PROVEN" src="https://img.shields.io/badge/make%20demo-must%20stay%20PROVEN-2F6BFF"></a>
  <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="TypeScript 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="ruff" src="https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black">
  <a href="LICENSE"><img alt="licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-D22128"></a>
</p>

[README](README.md) › **Contributing** · [Docs index](docs/README.md) · [Installation](docs/deployment/installation.md) · [Security policy](SECURITY.md)

---

**Thanks for considering it.** This page covers:

- how to get the project running
- what the tests expect
- the few places where the codebase has opinions worth knowing before you change them

> **One maintainer, in their own time.** SerpFlow is built and maintained by one person, so reviews are best-effort.
> Small, focused pull requests with a clear "why" get merged fastest.

## Getting set up

```bash
cp .env.example .env
make install        # uv venv on Python 3.13, plus npm install
make up             # postgres with pgvector, redis, kafka in KRaft mode
make upgrade        # alembic migrations
make seed           # catalog, benchmark fixtures, demo organization
make test           # 216 tests
```

- **No API keys are required**
  - planning uses a deterministic adapter
  - `test` API keys route to a deterministic SerpApi mock
  - so the whole project works offline
- Prerequisites for every OS: [installation guide](docs/deployment/installation.md)

## Before you open a pull request

```bash
make format         # ruff format + fix, prettier
make lint           # ruff check, eslint
make typecheck      # mypy, tsc
make test           # unit, integration and e2e
make demo           # the thesis must still hold
make docs-check     # if you touched docs: every link and path resolves
```

- **`make demo` exits non-zero if cache-aware replanning stops changing the selected plan**
- That is not a style check: **it is the product**

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
| The documentation | `docs/`, plus `scripts/build_docs_nav.py` for navigation |

## Changing the catalog

**The catalog is the single largest body of domain knowledge here**, and it has a defined authoring method.

- **`make catalog-build`** regenerates **drafts** from the SerpApi documentation into `data/_drafts/`
- **It never writes a committed file**, because two of the six steps cannot be automated:
  - **dependency edges:** a scraper can see that `google_maps_reviews` takes a `data_id`. Only a person decides that `google_maps.local_results[].data_id` is the field that satisfies it
  - **capability tags and substitutes:** grouping engines by what they actually compete on, and writing down the real trade-off, is judgement work
- **A substitute's `note` is user-facing copy:** it appears verbatim in Plan Inspector rejection reasons
  - "Different coverage" is not a note
  - "Sparse coverage outside US metros, and the reviewer identity shape differs, so contributor-history chaining is not available downstream" is
- **Run `make catalog-validate` after any catalog change**
  - every engine must declare substitutes, or state in `single_source_note` why nothing competes with it
  - so the planner can explain the absence instead of staying silent
- **Re-run `make benchmark`:** a catalog edit that improves one route often degrades another

More: [catalog architecture](docs/architecture/catalog.md)

## Changing the planner

**Two invariants the tests enforce:**

1. **Stage D emits multiple candidates wherever alternatives exist**
   - a single-candidate result is valid only when no alternative path exists, and the Plan must record `single_candidate_reason` saying why
   - if stage D routinely returns one plan, marginal replanning has nothing to re-rank
2. **Available is not acceptable**
   - a warm cache entry counts toward marginal savings only if it also meets the step's freshness requirement
   - relax that, and the planner will cheerfully serve a month-old price as a current one

- **Coverage is ranked before price:** a cheaper narrow-coverage substitute is no reason to answer a different question. Cost only breaks ties within a coverage band

More: [planner](docs/architecture/planner.md) · [marginal replanning](docs/architecture/marginal-replanning.md)

## Changing the cache

- **The entity and numeral guard is deliberately not a model call**
  - it extracts numerals, version identifiers and named entities from both queries, and requires exact set equality
  - it does not look at the similarity score at all
  - a model that is right 95% of the time still serves Indiranagar results for a Koramangala query once every twenty requests, and nobody reports that bug
- **If you change the guard**, `tests/unit/test_cache_guard.py` asserts the two cases the design exists for:
  - `iphone 16` never matches `iphone 17`
  - `restaurants in Koramangala` never matches `restaurants in Indiranagar`

More: [caching](docs/architecture/caching.md) · [ADR 0003](docs/adr/0003-deterministic-semantic-guard.md)

## Secrets

**Three rules, all tested:**

- **The upstream SerpApi credential is decrypted in exactly one place: the executor.** Decrypting it in an API handler means something went wrong upstream of that line
- **No response schema may contain a field that could carry it.** Not excluded: **absent**. `tests/unit/test_security.py` walks every Pydantic model in `app/schemas` and fails if one appears
- **The redaction filter runs on the log record, the formatted message and the exception path.** The leak path is always an exception handler

- **Never commit `.env`**, and never paste a real token into an issue, a PR or a log excerpt

More: [secrets](docs/security/secrets.md) · [credentials](docs/security/credentials.md)

## Database changes

**All schema changes go through Alembic.**

```bash
make migration ARGS="-m 'add thing'"
make upgrade
make downgrade      # confirm it reverses cleanly
```

- **Every tenant-scoped table needs:**
  - `org_id`, with an index
  - a row-level security policy: add it to `RLS_TABLES`, or enable it in the new migration as `0003_custom_roles` does
- **The application guards in `app/api/deps.py` are the primary check**; RLS is the backstop for the query somebody forgets to scope

More: [migrations](docs/database/migrations.md) · [row-level security](docs/database/rls.md)

## Changing the docs

- **Write short bullets, not paragraphs**, and link every claim to the code it describes
- **Navigation is generated.** After adding or renaming a page:

```bash
# add the page to ORDER (and its badges to PAGES) in scripts/build_docs_nav.py, then:
make docs-nav       # regenerate every page's badge header, breadcrumb and prev/next footer
make docs-check     # verify every relative link and repository path
```

- **The in-app docs renderer is a subset of markdown:** no HTML comments (they render as text), no task-list checkboxes, and no markdown image syntax inside a link. Badges are an HTML `<p>` of `<a><img></a>`
- **Check numbers against the code**, not against another doc. Counts drift; the code does not

## Tests

| Suite | Needs | Covers |
| --- | --- | --- |
| `tests/unit` (188) | nothing | catalog, path-finding, candidates, cost, freshness, guard, keys, credentials, RBAC, TTL, redaction |
| `tests/integration` | postgres, redis | the real app over HTTP, SSE frames, provenance headers, audit chain, bootstrap seeding |
| `tests/e2e` | postgres, redis | the thesis assertion, single-candidate reasoning, locale inference |

- **Integration and e2e tests skip themselves cleanly** when PostgreSQL is not reachable, so `make test` is useful on a laptop with nothing running
  - which also means a green run can hide them: use `pytest -rs` to see skip reasons
- **The benchmark is not part of CI.** It makes real LLM calls and runs on demand with `make benchmark`; results commit per catalog version under `backend/fixtures/benchmark/results/`

## Style

- **Python:** ruff, 100 columns, type hints on public functions
- **TypeScript:** strict mode, no `any` in exported types
- **Comments explain *why***, especially where the obvious implementation is wrong. Several places here silently produce a worse product in the straightforward version; those are commented
- **No emojis anywhere**, including commit messages, documentation and UI copy. Icons are Lucide, and never decorative sparkle or star glyphs

## Reporting a security issue

- **Please do not open a public issue.** See [SECURITY.md](SECURITY.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [README](README.md) | [Docs index](docs/README.md) | [Security policy](SECURITY.md) |
