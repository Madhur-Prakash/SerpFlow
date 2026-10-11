# Contributing to SerpFlow

<p>
  <a href="#getting-set-up"><img alt="setup: no API keys" src="https://img.shields.io/badge/setup-no%20API%20keys-3fcf8e"></a>
  <a href="#tests"><img alt="tests: 236 passing" src="https://img.shields.io/badge/tests-236%20passing-3fcf8e?logo=pytest&logoColor=white"></a>
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
make test           # 236 tests
```

- **No API keys are required**
  - planning uses a [deterministic adapter](docs/architecture/planner.md#stage-b-select)
  - `test` API keys route to a deterministic SerpApi mock ([execution modes](docs/product/execution-modes.md))
  - so the whole project works offline
- Prerequisites for every OS: [installation guide](docs/deployment/installation.md)
- Everyday targets, modes and real keys on a laptop: [local development](docs/deployment/local.md)
- Something fails on the way: [troubleshooting](docs/operations/troubleshooting.md#setup)

## Before you open a pull request

```bash
make format         # ruff format + fix, prettier
make lint           # ruff check, eslint
make typecheck      # mypy, tsc
make test           # unit, integration and e2e
make demo           # the thesis must still hold
make docs-check     # if you touched docs: every link, path and anchor resolves
```

- **`make demo` exits non-zero if cache-aware replanning stops changing the selected plan**
- That is not a style check: **it is the product**. What it proves: [the reference demo](docs/product/demo.md)
- The everyday targets, grouped: [local development](docs/deployment/local.md#everyday-targets)

## Where things live

| You want to change | Look in |
| --- | --- |
| What an engine can do, or what it chains to | `backend/app/services/catalog/data/v1/*.yaml` |
| How chains are computed | `backend/app/services/catalog/graph.py` |
| How candidates are generated and ranked | `backend/app/services/planner/` |
| Cache layers, the entity guard, TTL | `backend/app/services/cache/` |
| Execution order and credential handling | `backend/app/services/executor/` |
| Execution-mode precedence | `backend/app/services/runs.py`, `backend/app/integrations/serpapi/__init__.py` |
| Endpoints | `backend/app/api/v1/` |
| The Python SDK, CLI and MCP server | `backend/app/sdk/`, `backend/app/cli/`, `backend/app/mcp/` |
| The TypeScript SDK | `sdk/typescript/` |
| The control-plane UI | `frontend/src/pages/` |
| The documentation | `docs/`, plus `scripts/build_docs_nav.py` for navigation |

- How the pieces fit: [architecture overview](docs/architecture/overview.md) · [backend module map](docs/architecture/backend.md#module-map) · [frontend](docs/architecture/frontend.md) · [SDKs and tools](docs/sdks/overview.md)

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
- **Re-run `make benchmark`:** a catalog edit that improves one route often degrades another ([if you change the catalog](docs/product/benchmark.md#if-you-change-the-catalog))

More: [catalog architecture](docs/architecture/catalog.md#how-the-catalog-is-authored) · [ADR 0002: two edge sets](docs/adr/0002-typed-catalog-edges.md)

## Changing the planner

**Two invariants the tests enforce:**

1. **Stage D emits multiple candidates wherever alternatives exist**
   - a single-candidate result is valid only when no alternative path exists, and the Plan must record `single_candidate_reason` saying why
   - if stage D routinely returns one plan, marginal replanning has nothing to re-rank
2. **Available is not acceptable**
   - a warm cache entry counts toward marginal savings only if it also meets the step's freshness requirement
   - relax that, and the planner will cheerfully serve a month-old price as a current one

- **Coverage is ranked before price:** a cheaper narrow-coverage substitute is no reason to answer a different question. Cost only breaks ties within a coverage band

More: [planner](docs/architecture/planner.md) · [marginal replanning](docs/architecture/marginal-replanning.md) · [ADR 0008: coverage before price](docs/adr/0008-coverage-before-price.md) · [ADR 0009: freshness gates warmth](docs/adr/0009-freshness-gates-warmth.md) · [ADR 0014: persist every candidate](docs/adr/0014-persist-every-candidate.md)

## Changing the cache

- **The entity and numeral guard is deliberately not a model call**
  - it extracts numerals, version identifiers and named entities from both queries, and requires exact set equality
  - it does not look at the similarity score at all
  - a model that is right 95% of the time still serves Indiranagar results for a Koramangala query once every twenty requests, and nobody reports that bug
- **If you change the guard**, `tests/unit/test_cache_guard.py` asserts the two cases the design exists for:
  - `iphone 16` never matches `iphone 17`
  - `restaurants in Koramangala` never matches `restaurants in Indiranagar`

More: [caching](docs/architecture/caching.md#the-entity-and-numeral-guard) · [ADR 0003](docs/adr/0003-deterministic-semantic-guard.md)

## Secrets

**Three rules, all tested:**

- **The upstream SerpApi credential is decrypted only immediately before an upstream call:** in the executor for a search, and in the credential service for its validation and quota probes. Decrypting it in an API handler means something went wrong upstream of that line
- **No response schema may contain a field that could carry it.** Not excluded: **absent**. `tests/unit/test_security.py` walks every Pydantic model in `app/schemas` and fails if one appears
- **The redaction filter runs on the log record, the formatted message and the exception path.** The leak path is always an exception handler

- **Never commit `.env`**, and never paste a real token into an issue, a PR or a log excerpt

More: [secrets](docs/security/secrets.md) · [credentials](docs/security/credentials.md#where-it-is-decrypted) · [API keys](docs/security/api-keys.md) · [ADR 0006: absent, not excluded](docs/adr/0006-no-credential-field-in-schemas.md)

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

- **Read the autogenerated file before running it:** autogenerate does not produce HNSW indexes, RLS policies, triggers or backfills

More: [migrations: writing a new revision](docs/database/migrations.md#writing-a-new-revision) · [row-level security: adding a table](docs/database/rls.md#adding-a-table) · [ADR 0011](docs/adr/0011-rls-plus-application-guards.md)

## Changing the docs

- **Write short bullets, not paragraphs**, and link every claim to the code it describes
- **Link the first mention of a concept to its canonical page**, with a `#anchor` where a section covers it, and an ADR wherever the page describes a decision that has one
- **Every page ends with `## Related`** (ADRs keep `## See also`): at least three links, each with a reason, including pages from other sections
- **A new term goes in the [glossary](docs/product/glossary.md)**, with a link to the page that explains it
- **Navigation is generated.** Never edit a page's badge header, breadcrumb or previous/next footer by hand. After adding or renaming a page:

```bash
# add the page to ORDER (and its badges to PAGES) in scripts/build_docs_nav.py, then:
make docs-nav       # regenerate every page's badge header, breadcrumb and prev/next footer,
                    # and the docs browser's reading order
make docs-check     # every link, cited path and #anchor resolves; every page has a
                    # Related section and is linked from another page's body
```

- **The in-app docs renderer is a subset of markdown:** no HTML comments (they render as text), no task-list checkboxes, and no markdown image syntax inside a link. Badges are an HTML `<p>` of `<a><img></a>`. Root files such as this one are rendered there too. See [the documentation browser](docs/architecture/web.md#the-documentation-browser)
- **Check numbers against the code**, not against another doc. Counts drift; the code does not
- **A decision whose alternative was genuinely defensible gets an ADR:** numbered next in sequence, with the five parts (context, decision, alternatives rejected, cost, see also), added to the table in the ADR index and to `ORDER`. See [writing a new one](docs/adr/README.md#writing-a-new-one)

## Tests

| Suite | Needs | Covers |
| --- | --- | --- |
| `tests/unit` (208) | nothing | catalog, path-finding, candidates, cost, freshness, guard, keys, credentials, RBAC, TTL, redaction, execution modes, email, real SerpApi response shapes, the SDK, CLI and MCP entry points |
| `tests/integration` (25) | postgres, redis | the real app over HTTP, SSE frames, provenance headers, audit chain, bootstrap seeding |
| `tests/e2e` (3) | postgres, redis | the thesis assertion, single-candidate reasoning, locale inference |

- **Integration and e2e tests skip themselves cleanly** when PostgreSQL is not reachable, so `make test` is useful on a laptop with nothing running
  - which also means a green run can hide them: use `pytest -rs` to see skip reasons ([troubleshooting](docs/operations/troubleshooting.md#integration-tests-all-report-skipped))
- **`tests/unit/test_email.py` expects no Gmail credential:** with `GMAIL_CREDENTIALS_B64` set in your `.env`, the console-transport test fails. Unset it for the run ([email: testing](docs/operations/email.md#testing))
- **The benchmark is not part of CI.** With `LLM_PROVIDER=groq` it makes real model calls; it runs on demand with `make benchmark`, and results commit per catalog version under `backend/fixtures/benchmark/results/` ([running it](docs/product/benchmark.md#running-it))

## Style

- **Python:** ruff, 100 columns, type hints on public functions
- **TypeScript:** strict mode, no `any` in exported types
- **Comments explain *why***, especially where the obvious implementation is wrong. Several places here silently produce a worse product in the straightforward version; those are commented
- **No emojis anywhere**, including commit messages, documentation and UI copy. Icons are Lucide, and never decorative sparkle or star glyphs

## Reporting a security issue

- **Please do not open a public issue.** See [SECURITY.md](SECURITY.md), and the [threat model](docs/security/threat-model.md) for what is in and out of scope

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [README](README.md) | [Docs index](docs/README.md) | [Security policy](SECURITY.md) |
