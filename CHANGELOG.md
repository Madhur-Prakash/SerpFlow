# Changelog

All notable changes to SerpFlow are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Startup bootstrap.** `RUN_MIGRATIONS_ON_STARTUP` applies Alembic migrations
  when the API starts, and `SEED_ON_STARTUP` runs the idempotent seed, so a
  container plus an empty database becomes a working instance with no
  orchestration step. Both default to false. Both take a PostgreSQL advisory
  lock, so several replicas starting together cannot race, and seeding is
  refused automatically when `ENVIRONMENT` is staging or production. See
  `docs/operations/bootstrap.md`.
- **Email.** Transactional mail through the Gmail API, selected by setting
  `GMAIL_CREDENTIALS_B64` and nothing else; with it empty, messages go to the
  log so `make dev` still needs no keys. Jinja2 templates, autoescaped, text
  and HTML. `backend/scripts/mint_gmail_token.py` produces the credential. See
  `docs/operations/email.md`.
- **`TRUSTED_PROXY_HOPS`.** How many proxies in front of the API append to
  `X-Forwarded-For`. The address is now read that many entries from the right,
  so a client-supplied header can no longer forge a caller identity.
- Surface tests for the CLI, the MCP server and both SDKs; email and bootstrap
  test suites. 115 tests to 180.
- `sdk/README.md` and `sdk/typescript/README.md`.

### Fixed

- **The MCP server could not start.** `mcp` 2.x renamed `FastMCP` to
  `MCPServer`, and nothing in the suite imported `app.mcp.server`, so
  `serpflow-mcp` was failing at startup while every other test passed. The
  import now works on both majors, and a test asserts the four tools load.
- **Email verification and password reset were unusable end to end.**
  `register` minted a verification token and discarded the plaintext;
  `forgot-password` stored a reset hash that nothing ever mailed. Both now
  send. An `email` notification channel was created and then marked `skipped`
  by the webhook worker; it now delivers.
- **The backend image did not ship `fixtures/`.** Compose bind-mounts that
  directory, which hid it; a bare `docker run` of the image failed to seed.
- Alembic's `env.py` called `fileConfig()`, which disables every existing
  logger. Running migrations in-process silenced the application's own logging
  for the rest of the process, including the error that came next.
- `ruff`'s `exclude` was replacing the default ignore list rather than
  extending it, so `.venv` was being linted — 37,831 findings hiding 47 real
  ones, all now fixed, along with 23 real mypy errors.

- **A public web surface.** A landing page that tells the thesis as a pinned,
  scrubbed scroll story; a documentation browser at `/docs` rendered from the
  repository's own markdown; and an API reference at `/api` generated from the
  OpenAPI schema. GSAP, SplitText and ScrollTrigger load on demand, so the
  console downloads none of it. See `docs/architecture/web.md`.
- **Light theme, and a theme control.** Three states (dark, light, system,
  defaulting to system), switched with a View Transitions circle reveal from
  the control that was pressed. An inline script applies the stored theme
  before the first paint, so there is no flash. The light theme is a separate
  design rather than a tinted inversion: the accent darkens to hold contrast on
  white and shadows take over the structural work borders do on a dark ground.
- `make test-ui` renders every public page in a real browser in both themes and
  fails on console errors or on any element a scroll reveal left invisible.
- `make api-reference` regenerates the reference page; `make docs-check`
  verifies that all 374 relative links and 95 cited paths resolve.

### Changed

- `MAX_REQUEST_BYTES` is now `MAX_REQUEST_BODY_BYTES`, default 1 MiB.
- The README header is centred, with badges and a contents table, and every
  README now links to the others.
- The backend image no longer runs `alembic upgrade head` from its `CMD`. A
  shell command in front of the server cannot hold an advisory lock, so
  migration moved into the application's startup path.

## [0.1.0] - 2026-10-02

First release. SerpFlow routes a natural-language intent to the right SerpApi
engine or engine chain, re-plans around what is already cached, and executes
only the searches that still need a live call.

### Engine catalog

- 54 hand-reviewed engines committed as versioned YAML under
  `backend/app/services/catalog/data/v1/`, covering the Google family, the
  major alternative web engines, the commerce verticals, the scholarly and
  patent chains, and the app stores.
- 30 typed dependency edges and 69 substitute edges across 28 capability tags.
  Both edge kinds are mandatory: dependency edges make multi-hop chains
  computable, substitutes make alternative plans generatable.
- `make catalog-build` regenerates drafts from the SerpApi documentation. The
  committed catalog remains the source of truth; the two steps a scraper
  cannot do - deriving dependency edges and grouping engines into substitute
  families - stay hand-maintained.
- `make catalog-validate` lints every engine for a purpose, capability tags,
  required parameters, and either substitutes or an explicit
  `single_source_note`.

### Planner

- Four stages: retrieval, selection, synthesis and path-finding.
- Retrieval scores capability affinity against the words people actually use,
  not only embedding similarity, and expands the shortlist with substitutes of
  strong matches so competing engines enter the candidate set.
- Path-finding walks typed edges backwards from a target until every required
  parameter is either caller-supplied or produced upstream. The model never
  invents a chain.
- Stage D emits multiple candidate plans. A single-candidate result records
  `single_candidate_reason` explaining why no alternative exists.
- Freshness inference classifies every step as `realtime`, `fresh`, `recent` or
  `stable` from temporal language, the engine's volatility prior and the query
  class.
- Entity resolution turns city names into IATA codes so flight intents are
  routable, and resolves relative dates including weekdays and month
  qualifiers.

### Marginal-cost replanning

- Candidates are ranked twice, once on cold cost and once on marginal cost.
  When the rankings disagree the fact is persisted on the Plan and counted in
  `serpflow_marginal_replan_changed_selection_total`.
- Coverage is ranked before price: a narrow-coverage substitute being cheaper
  is not a reason to answer a different question.
- A warm cache entry counts toward marginal savings only when it also satisfies
  the step's freshness requirement.
- Budget-aware reduction runs before the final ranking, so candidates are
  compared at the costs they would actually execute at. Every reduction carries
  a human-readable impact note.

### Cache

- Four layers: exact in Redis, semantic in PostgreSQL with pgvector and an HNSW
  index, the SerpApi Searches Archive, then live.
- Semantic lookups filter on partition, engine and locale columns before any
  vector distance is computed.
- A deterministic entity and numeral guard rejects any semantic hit whose
  numeral, version or named-entity sets differ, regardless of cosine score.
  Every rejection is logged so the threshold can be tuned with evidence.
- Adaptive TTL seeded from each engine's volatility prior and learned per
  engine and query class: an unchanged top ten extends the TTL by half again,
  significant churn halves it.
- Redis is explicitly not the source of truth. A restart repopulates lazily
  from the durable PostgreSQL index and loses no credits.

### Execution

- Per step: exact, then semantic, then the Searches Archive, then live.
- Upstream credentials are decrypted in exactly one place, the executor.
- A credential revoked mid-run fails the run loudly rather than returning
  partial results.
- Large payloads go to content-addressable object storage; identical responses
  deduplicate.

### Identity, budgets and governance

- Organizations, projects, members and project-level role overrides.
- Five roles. Analysts can plan but not execute: planning calls a language
  model rather than SerpApi, so it spends nothing.
- API keys in the form `sf_<env>_<project prefix>_<secret>`, hashed with
  HMAC-SHA256 under a server-side pepper, with rotation, grace periods and
  immediate revocation.
- `test` API keys always route to the deterministic mock and consume zero
  SerpApi credits, whatever `SERPFLOW_MODE` says.
- Upstream credentials under envelope encryption with project-to-organization
  inheritance, validation on save, and atomic rotation.
- Budgets at organization, project, API key and session scope, with three
  exhaustion modes.
- `BUDGET_EXHAUSTED` and `UPSTREAM_QUOTA_EXHAUSTED` are distinct errors with
  distinct fixes, and upstream quota reconciliation surfaces divergence rather
  than hiding it.
- Append-only, hash-chained audit log with verification and export.
- Project-level cache isolation by default; organization-level sharing is
  opt-in and attributes spend and savings separately.

### Interfaces

- REST API with OpenAPI, SSE streaming, and provenance headers on every
  response.
- Server-Sent Events emitting one frame per real backend stage transition. The
  UI pipeline animation is driven entirely by these frames.
- MCP server exposing `search`, `plan`, `explain` and `catalog` on the same
  service layer, with full service-principal session resolution.
- Python and TypeScript SDKs, both including a SerpApi-compatible drop-in.
- CLI covering search, plan, replay, catalog exploration, cache inspection and
  the benchmark.
- Control-plane UI: overview, search, runs, Run Inspector, Plan Inspector,
  Catalog Explorer, cache dashboard, budgets, analytics, benchmarks, audit log
  and settings.

### Observability

- OpenTelemetry traces spanning retrieval, selection, path-finding, candidate
  generation, marginal costing and execution down to the upstream call.
- 20 Prometheus metrics, each with a real producer.
- Logifyx structured JSON logging with a credential redaction filter covering
  the exception path, asserted by tests.

### Benchmark

- 120 hand-authored labelled tasks committed as versioned fixtures, covering
  single-engine routing, multi-hop chains, locale inference, freshness
  sensitivity and substitute selection.
- Three systems scored on the same set: an unaided model with no catalog,
  embedding retrieval with no selector or path-finding, and the full pipeline.
- Results commit per catalog version. Not part of CI, because it needs real
  LLM calls.

### Infrastructure

- Docker Compose with PostgreSQL 17 and pgvector, Redis, Kafka 4.x in KRaft
  mode, and optional MinIO, Prometheus and Grafana profiles.
- Alembic migrations including row-level security policies, the HNSW vector
  index and the audit-log append-only trigger.
- 115 tests across unit, integration and end-to-end suites, including an
  explicit assertion that cache state changed which plan was selected.

### Documentation

- A documentation tree under `docs/`, indexed by `docs/README.md`, covering
  architecture, the API, the database, security, deployment, operations and
  the product. Every page links to the implementation path it describes.
- Fourteen architecture decision records under `docs/adr/`, each stating the
  alternative that was rejected and the cost that was accepted.

[Unreleased]: https://github.com/serpflow/serpflow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/serpflow/serpflow/releases/tag/v0.1.0
