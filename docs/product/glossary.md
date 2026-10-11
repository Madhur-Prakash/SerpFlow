# Glossary

<p>
  <a href="../product/README.md"><img alt="docs: Product" src="https://img.shields.io/badge/docs-Product-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="terms: 110" src="https://img.shields.io/badge/terms-110-2F6BFF">
  <a href="../../backend/app/api/deps.py"><img alt="source: api/deps.py" src="https://img.shields.io/badge/source-api%2Fdeps.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 30 min" src="https://img.shields.io/badge/read-30%20min-555555">
</p>

[Docs](../README.md) › [Product](../product/README.md) › **Glossary** · page 6 of 50

**Every term these docs use, defined once, in the sense SerpFlow uses it.** Each entry is a sentence or two, then a link to the page that covers it in depth. Codes, tables, headers and metrics keep their exact spelling, so a term found here can be searched for in the code.

## A

- **Absent, not excluded**: The rule that no Pydantic response model in `app/schemas` has a field that could carry an upstream credential, rather than having one marked `exclude=True`. A test walks every response model to enforce it. [Upstream credentials: never in a response](../security/credentials.md#never-in-a-response)
- **Access token**: A 15-minute JWT issued by `POST /v1/auth/login` and sent as `Authorization: Bearer`; a 14-day refresh token renews it. It is the only credential the SSE stream accepts as an `?access_token=` query parameter. [API overview: authentication](../api/overview.md#authentication)
- **Adaptive TTL**: How long a cache entry lives. It starts at the engine's volatility prior, is multiplied by 1.5 when a refresh finds the top 10 results unchanged and by 0.5 when 3 or more of them moved, and is clamped between 5 minutes and 90 days. It is learned per engine and query class, and never outlives the step's freshness requirement. [Caching: adaptive TTL](../architecture/caching.md#adaptive-ttl)
- **Advisory lock**: The PostgreSQL lock the startup bootstrap takes before migrating or seeding, so replicas that start together wait for one another instead of racing. Migration and seeding use distinct keys. [Startup bootstrap: an advisory lock](../operations/bootstrap.md#1-an-advisory-lock)
- **Alert**: An in-application record raised for budget thresholds, exhaustion, upstream quota and false hits. It travels on the `serpflow.alerts` topic, is deduplicated by `dedupe_key`, and is delivered to the organization's notification channels (email, webhook or Slack). [Observability: alerting](../operations/observability.md#alerting)
- **API key**: The credential a caller presents to SerpFlow, shaped `sf_<env>_<project_prefix>_<secret>`. The project prefix is stored in plaintext for an indexed lookup; the secret is stored only as an HMAC-SHA256 under the pepper, and is shown once, at creation. [API keys: format](../security/api-keys.md#format)
- **Application guards**: The checks in [`app/api/deps.py`](../../backend/app/api/deps.py) that compare every resource fetched by id against the caller's `org_id`, and answer `404`, never `403`, across tenants. They are the primary tenant-isolation check; row-level security is the backstop. [Row-level security: the application guards](../database/rls.md#the-application-guards)
- **Audit log**: The `audit_log` table. A trigger makes it append-only (it refuses `UPDATE`, and refuses `DELETE` unless the transaction set `app.audit_purge`), and a per-organization hash chain lets `GET /v1/audit/verify` report the first break. [Row-level security: the audit log](../database/rls.md#the-audit-log)
- **Available is not acceptable**: The cost model's central rule: a cached entry counts as warm only if it also meets the step's freshness requirement. An entry that exists but is too old is costed as a live call. [Marginal-cost replanning: available is not acceptable](../architecture/marginal-replanning.md#available-is-not-acceptable)

## B

- **Beneficiary project**: The project a cache hit saved credits for. The ledger records it as `beneficiary_project_id`, separately from the `project_id` that paid for the fetch, so the benefit of a shared organization cache is a computed figure. [Database schema: governance](../database/schema.md#governance)
- **Binding**: How each step's parameters get their values. A root binding comes from the caller (the intent's query, locale and location, mapped onto whatever the engine calls them); a chain binding is a placeholder the executor fills from the upstream step's real payload, one call per value, failing the step with `BINDING_FAILED` if there is none ([`graph.py`](../../backend/app/services/catalog/graph.py)). [The planner: stage C](../architecture/planner.md#stage-c-synthesize) · [The executor: fan-out and binding](../architecture/executor.md#fan-out-and-binding)
- **Budget**: A credit cap at one of four scopes (organization, project, API key, service session) over a daily, weekly, monthly or total period. The tightest applicable budget wins, and it is checked before every live call. Each budget also stores an exhaustion mode (`stale`, `error` or `queue`), but enforcement currently refuses with `BUDGET_EXHAUSTED` whichever it holds ([`budgets/service.py`](../../backend/app/services/budgets/service.py)). [The executor: budget enforcement](../architecture/executor.md#budget-enforcement)
- **Budget-aware reduction**: What the planner does, before ranking, to a candidate that does not fit the budget: it scales fan-out proportionally across the widened steps, drops terminal steps only if that cannot fit, and attaches an impact note to every cut. If nothing fits, it raises `BUDGET_INFEASIBLE`. [Marginal-cost replanning: budget-aware reduction](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking)
- **`BUDGET_EXHAUSTED` and `UPSTREAM_QUOTA_EXHAUSTED`**: Two errors that are never conflated. The first means your own SerpFlow cap is spent (raise it); the second, that the SerpApi account itself is out (buy upstream capacity). [Troubleshooting: BUDGET_EXHAUSTED against UPSTREAM_QUOTA_EXHAUSTED](../operations/troubleshooting.md#budget_exhausted-against-upstream_quota_exhausted)
- **BYOK**: Bring your own key. Every upstream call is authenticated with a SerpApi or Groq key the organization supplied, stored encrypted per organization; the deployment holds no SerpApi key of its own to fall back to. [Bring your own key](../security/byok.md)

## C

- **Cache layer**: One of the four places a step can be served from, tried in order: exact, semantic, Searches Archive, live. Only the live layer spends credits. The layer that served a step is recorded on it and returned in `X-SerpFlow-Cache`. [Caching](../architecture/caching.md)
- **Cache state**: What `inspect()` reports for one step of one candidate: whether an entry is available, whether it is acceptable under the step's freshness requirement, and a sentence explaining any gap between the two. Marginal cost is computed from it. [Marginal-cost replanning: available is not acceptable](../architecture/marginal-replanning.md#available-is-not-acceptable)
- **Candidate plan**: One of the competing plans stage D generates for an intent, by strategy `primary`, `substitute` or `shallow` (a truncation of a longer chain). Plans that end at the capability the intent asks for compete as answers; the rest are fallbacks that win only when nothing else fits the budget. Every candidate is persisted in `plan_candidates`, losers with a rejection reason. [The planner: candidate plurality](../architecture/planner.md#candidate-plurality-is-a-hard-requirement)
- **Capability tag**: A catalog label for what an engine does, such as `place_reviews`. Engines that share a tag compete as substitutes. The capability vocabulary maps each tag to the words people actually use, and that affinity carries 0.72 of the retrieval score. Catalog v1.0.0 has 28. [The engine catalog: the capability vocabulary](../architecture/catalog.md#the-capability-vocabulary)
- **Cassette**: A recorded SerpApi response, written as one JSON file per engine and parameter set under `fixtures/cassettes/` in the backend when the mode is `record`, and served when it is `replay` ([`cassettes.py`](../../backend/app/integrations/serpapi/cassettes.py)). None are committed. [Execution modes: the four modes](execution-modes.md#the-four-modes)
- **Catalog**: The versioned YAML under [`backend/app/services/catalog/data/v1/`](../../backend/app/services/catalog/data/v1) describing every engine SerpFlow can route to: parameters, produced fields, cost, volatility, PII risk, capability tags and substitutes. It is the source of truth: `make seed` projects it into the `catalog_*` tables, and every plan records the `catalog_version` it used. Version 1.0.0 has 54 engines. [The engine catalog](../architecture/catalog.md)
- **Catalog Explorer**: The console page at `/app/catalog` that draws the catalog as a graph: dependency edges as solid arrows, substitute edges as dashed lines. [The engine catalog: Catalog Explorer](../architecture/catalog.md#catalog-explorer)
- **Changed selection**: `marginal_replan_changed_selection` on a plan: true when marginal ranking chose a different plan from cold ranking. It is persisted, counted by `serpflow_marginal_replan_changed_selection_total` (the thesis metric), and asserted by `make demo` and the e2e suite. [Marginal-cost replanning: what changed_selection means](../architecture/marginal-replanning.md#what-changed_selection-means) · [Observability: the thesis metric](../operations/observability.md#the-thesis-metric)
- **Cold cost**: Also naive cost (`naive_cost`): what a plan would cost with nothing cached, unit cost times fan-out summed over its steps. Cold ranking orders candidates on it, and the plan it would have chosen is stored as `cold_winner_candidate_id`. [Marginal-cost replanning: ranking](../architecture/marginal-replanning.md#ranking)
- **Coverage**: How fully a substitute serves the same capability: `full` (an equivalent result set), `partial` (overlapping, but materially different coverage or field shape) or `narrow` (usable only inside a restricted geography, vertical or corpus). [The engine catalog: coverage and notes](../architecture/catalog.md#coverage-and-notes)
- **Coverage before price**: The ranking rule that coverage is the primary sort key and cost only breaks ties within a coverage band, so a narrow 11-credit route never beats a full 101-credit one. Narrow plans stay in the set as budget fallbacks. [Marginal-cost replanning: coverage before price](../architecture/marginal-replanning.md#coverage-before-price)
- **Credit**: SerpApi's billing unit: a live search costs one. Every figure SerpFlow reports (naive, marginal, spent, saved, budgets) is in credits, from each engine's catalog `cost` times its fan-out. [Marginal-cost replanning: costing a step](../architecture/marginal-replanning.md#costing-a-step)
- **Custom role**: An organization-defined role holding a chosen set of permissions from `GET /v1/roles/permissions`, stored in `custom_roles` (migration `0003`) under row-level security. A membership's or API key's `role` holds either a built-in role name or a custom role's slug. [API keys: custom roles](../security/api-keys.md#custom-roles)

## D

- **Degradation**: How SerpFlow behaves when a dependency other than PostgreSQL is down: Redis lookups fall through to the durable index and rate limiting fails open, Kafka drops background events with one warning, and a missing payload object is treated as a cache miss. `/readyz` returns 503 only for PostgreSQL. [Backend: degradation](../architecture/backend.md#degradation)
- **Dependency edge**: A typed link saying that a field one engine produces satisfies a parameter another requires (`satisfied_by` / `feeds`), with a `fan_out_hint`. Dependency edges are how engines chain, and what makes a multi-hop path computable; catalog v1.0.0 has 30. [The engine catalog: both relationship kinds are mandatory](../architecture/catalog.md#both-relationship-kinds-are-mandatory)
- **Deterministic adapter**: The rule-based stage B selector ([`mock.py`](../../backend/app/integrations/llm/mock.py)), used whenever the organization has brought no Groq key and the instance does not set `LLM_PROVIDER=groq`. It scores the retrieved shortlist on capability vocabulary and locale, makes no network call, returns the same plan for the same intent, and produced the published 38.3%. [Routing benchmark: read this before quoting the number](benchmark.md#read-this-before-quoting-the-number)
- **Deterministic mock**: The SerpApi stand-in that a `test` API key always reaches. It generates deterministic results, makes no network call, costs zero credits, and marks responses `X-SerpFlow-Mode: MOCK`; the `mock` mode cannot be chosen any other way. [Execution modes: why mock is not selectable](execution-modes.md#why-mock-is-not-selectable)
- **Drill-down engine**: An engine reachable only through another engine's identifier, such as `google_patents_details`. The selector penalises it unless the second hop adds a capability the first lacks. [The planner: stage B](../architecture/planner.md#stage-b-select)

## E

- **Engine**: One SerpApi search API, such as `google_maps` or `yelp_reviews`, as described by its catalog entry. Engines are what the planner chains, compares and costs. [The engine catalog: what an engine entry declares](../architecture/catalog.md#what-an-engine-entry-declares)
- **Engine policy**: A project's engine allowlist and denylist. A denied engine is excluded during planning and checked again before execution, where it fails with `ENGINE_NOT_ALLOWED`. [The executor: engine policy](../architecture/executor.md#engine-policy)
- **Entity and numeral guard**: The deterministic check a semantic hit must pass: numerals, version identifiers and named entities are extracted from both queries and must match as exact sets, whatever the cosine score. Each refusal is written to `semantic_guard_rejections` and counted by reason. [Caching: the entity and numeral guard](../architecture/caching.md#the-entity-and-numeral-guard)
- **Envelope encryption**: How upstream credentials are stored. Each gets its own random AES-256-GCM data key (DEK), which a key-encryption key (KEK) wraps; only the ciphertext and the wrapped DEK are stored, so rotating the KEK rewraps DEKs without touching the ciphertext. [Upstream credentials: envelope encryption](../security/credentials.md#envelope-encryption)
- **Error envelope**: The body of every error response, `{"error": {"code", "message", "request_id"}}`, with a stable machine code from [`core/exceptions.py`](../../backend/app/core/exceptions.py) and never a stack trace. [API overview: errors](../api/overview.md#errors)
- **Exact layer**: The first cache layer: a lookup by the hash of the normalised request, served from Redis and backed by the durable `cache_entries` index in PostgreSQL, so a Redis miss is not a cache miss. [Caching: the Redis boundary](../architecture/caching.md#the-redis-boundary)
- **Execution mode**: Where a result comes from, and whether it costs anything: `live`, `record`, `replay` (the default) or `mock`. It is resolved per request, recorded on the run and each step, and returned in `X-SerpFlow-Mode`. [Execution modes](execution-modes.md)

## F

- **False-hit report**: An operator's report, from the Run Inspector or `POST /v1/runs/{id}/report-false-hit`, that a semantic hit served the wrong thing. It is stored in `false_hit_reports`, increments `serpflow_semantic_false_hit_reports_total`, and can invalidate the entry. [Caching: invalidation](../architecture/caching.md#invalidation)
- **Fan-out**: How many calls a step makes: one per value the upstream step produced, capped at the step's fan-out. The catalog's `fan_out_hint` estimates it, and hints propagating along a chain are where the reference demo's 101 credits come from (1 + 20 + 20 × 4). [The engine catalog: the reference demo chain](../architecture/catalog.md#the-reference-demo-chain)
- **Fingerprint**: `sha256(secret)[:8]` of an upstream credential: the non-reversible value the console, the audit log and the quota metrics use to tell credentials apart. [Upstream credentials: the fingerprint](../security/credentials.md#the-fingerprint)
- **Free tier**: SerpApi's 250 searches a month. The defaults are sized to fit it: `make seed` creates a 250-credit organization budget, the demo runs against the mock, and the 101-credit chain is only ever a projection. [The reference demo: the full-scale figure](demo.md#the-full-scale-figure)
- **Freshness requirement**: The maximum age a cached entry may have for one step, as one of four classes: `realtime` (under 15 minutes), `fresh` (under 24 hours), `recent` (under 7 days) or `stable` (any valid TTL). Stage C infers it per step from temporal language, the engine's volatility prior and the query class, and the strictest signal wins. [The planner: freshness inference](../architecture/planner.md#freshness-inference)

## G

- **Grace window**: The overlap after a rotation during which the old and new secrets both work: 60 minutes for an API key (`rotation_grace_until`), 15 minutes for an upstream credential (`grace_until`). A `DELETE` revokes with no window. [API keys: rotation](../security/api-keys.md#rotation) · [Upstream credentials: validation and revocation](../security/credentials.md#validation-and-revocation)
- **Groq adapter**: The model-driven stage B selector ([`groq.py`](../../backend/app/integrations/llm/groq.py)), used when the organization has brought a Groq key, or when a self-hosted instance sets `LLM_PROVIDER=groq` with `GROQ_API_KEY`. It may only choose among retrieved engines: any other engine it names is dropped and recorded as `hallucinated: true`. [The planner: stage B](../architecture/planner.md#stage-b-select) · [Bring your own key: the self-hosting exception](../security/byok.md#the-self-hosting-exception)

## H

- **HNSW**: The pgvector approximate-nearest-neighbour index on `cache_entries.embedding` (`m=16`, `ef_construction=64`, cosine). The semantic query filters on the partition columns first, so HNSW only orders rows already inside the caller's partition. [Caching: partitioning](../architecture/caching.md#partitioning)

## I

- **Impact note**: The sentence every budget reduction carries, written per capability in [`budget.py`](../../backend/app/services/planner/budget.py), saying what the cut loses: lower ring-detection recall, for example, when contributor sampling drops from 80 calls to 12. [Marginal-cost replanning: every reduction carries an impact note](../architecture/marginal-replanning.md#every-reduction-carries-an-impact-note)
- **`inspect()` and `lookup()`**: The cache's two entry points. The planner calls `inspect()`, read-only, for every step of every candidate before choosing; the executor calls `lookup()` for the step it is about to run, which records guard rejections and repopulates Redis. [Caching: two entry points](../architecture/caching.md#two-entry-points)
- **Intent**: The natural-language question a caller sends to `POST /v1/plan` or `POST /v1/search`, 3 to 2,000 characters. The planner turns it into engines, parameters and freshness requirements. [API overview: core endpoints](../api/overview.md#core-endpoints)

## K

- **Kafka topic**: One of eight `serpflow.*` topics carrying background work only: scheduled and bulk runs, cache refresh, credential validation, quota reconciliation, analytics, alerts, webhooks and catalog reload. The broker runs in KRaft mode, with no ZooKeeper, and interactive search never goes through it. [Kafka: topics](../operations/kafka.md#topics)
- **KEK**: The key-encryption key that wraps every credential's DEK: `CREDENTIAL_KEK` locally, a KMS in production. It lives only in the process environment, never in the database, and `kek_id` records which KEK wrapped each row. [Secrets: KEK](../security/secrets.md#kek)

## L

- **Ledger**: `budget_ledger`, one row per spend (a live call) or saving (`routing`, `exact`, `semantic` or `archive`), carrying both the fetching `project_id` and the `beneficiary_project_id`. Savings by mechanism and spend attribution are computed from it. [Database schema: governance](../database/schema.md#governance)
- **Live, record and replay**: The three selectable execution modes. `live` calls SerpApi and spends credits; `record` does the same and also writes cassettes; `replay`, the default, serves cassettes only, never reaches the network, and fails a miss with `REPLAY_CASSETTE_MISS`. [Execution modes: the four modes](execution-modes.md#the-four-modes) · [Troubleshooting: REPLAY_CASSETTE_MISS](../operations/troubleshooting.md#replay_cassette_miss)
- **Locale inference**: Stage C's rule-based mapping from places in the intent to SerpApi's `gl` and `hl` (Seoul gives `gl=kr`, `hl=ko`), checking districts before cities. Temporal phrases such as "right now" or "at least" are never taken as a place, and a place ends at the next listed break word such as "at" or "for" ([`text.py`](../../backend/app/core/text.py)). [The planner: stage C](../architecture/planner.md#stage-c-synthesize) · [temporal phrases are not places](../architecture/planner.md#temporal-phrases-are-not-places)

## M

- **Marginal cost**: What a plan costs given the current cache state: only the steps that still need a live call, counting a warm entry only if it meets the step's freshness requirement. Marginal ranking orders candidates on it, and its winner is the plan that executes. [Marginal-cost replanning: the distinction](../architecture/marginal-replanning.md#the-distinction)
- **MCP server**: `serpflow-mcp`, which gives an LLM agent four tools (`plan`, `search`, `explain`, `catalog`) over stdio. It runs the service layer in its own process against the API's database rather than calling the API, and each agent runs under a service session. [MCP server](../sdks/mcp.md) · [MCP server: connect a client](../sdks/mcp.md#connect-a-client)
- **Mode precedence**: The order a run's execution mode resolves in: a `test` key always means mock, absolutely; then a per-request `mode`; then the project's own mode; then `SERPFLOW_MODE`. The last three resolve in one function, `resolve_execution_mode`, and an unrecognised mode resolves to `replay`. [Execution modes: who chooses, and precedence](execution-modes.md#who-chooses-and-precedence)

## N

- **Normalisation**: What happens to a request before it is hashed for the exact layer: whitespace collapsed, case folded, accents stripped, parameters stably ordered, and non-semantic parameters (`api_key`, `output`, `no_cache`, `async`, `zero_trace`) removed. [Caching: normalisation](../architecture/caching.md#normalisation)
- **Notice**: SerpApi's message for a search it processed but found nothing for, such as "Google Finance hasn't returned any results for this query". SerpFlow treats it as a successful, billed, empty search: the credit is recorded, the result is cached, and the message reaches the result panel as `summary.notice`, up to 300 characters ([`client.py`](../../backend/app/integrations/serpapi/client.py), [`executor/service.py`](../../backend/app/services/executor/service.py)). [The executor: an empty answer is still a billed answer](../architecture/executor.md#an-empty-answer-is-still-a-billed-answer) · [Caching: billed empty results](../architecture/caching.md#billed-empty-results)

## O

- **Object storage**: Where large SERP payloads live: the filesystem by default, S3 or MinIO when configured. Keys are the SHA-256 of the gzipped body, so identical responses deduplicate, and PostgreSQL holds only the `payload_ref`. [Caching: object storage](../architecture/caching.md#object-storage)
- **Organization**: The top-level tenant. It owns projects, members, roles, credentials, budgets and its own audit chain, and every tenant-scoped row carries its `org_id`. [Architecture overview: tenancy](../architecture/overview.md#tenancy)

## P

- **Partition key**: The cache's isolation boundary: `project:<id>` by default, or `org:<id>` when a project opts into organization-level sharing. Semantic lookups filter on it, with engine, `gl`, `hl` and location, before any vector distance is computed, and it never spans organizations. [Caching: partitioning](../architecture/caching.md#partitioning)
- **Path-finding**: Stage D's walk backwards over dependency edges from a target engine, until every required parameter is either caller-suppliable or produced upstream. A parameter that cannot be sourced invalidates the path: the planner never guesses a value. [The planner: stage D](../architecture/planner.md#stage-d-path-find-and-generate-candidates)
- **Payload**: The raw SERP JSON for a step, stored content-addressed in object storage and referenced by `payload_ref`. Reading it needs the `payload:read` permission, separate from seeing the run, because it can contain personal data. [The executor: per-step record](../architecture/executor.md#per-step-record)
- **Pepper**: `API_KEY_PEPPER`, the server-side secret API keys are HMAC'd under. It is never stored in the database, so a dump cannot verify a guessed key; rotating it means rotating every API key. [Secrets: pepper](../security/secrets.md#pepper)
- **Permission**: A named capability such as `run:execute`, `run:mode_override` or `payload:read`, granted through a role and asserted by `require(...)` on each route. Anything not granted is denied. [API keys: checks are centralised](../security/api-keys.md#checks-are-centralised)
- **PII risk**: An engine's `pii_risk`: `low`, `medium` or `high`. A run inherits the highest level of any step it ran, as `max_pii_risk`, and `high` shortens retention to 7 days. [The engine catalog: volatility and PII](../architecture/catalog.md#volatility-and-pii)
- **Plan**: The persisted output of planning: steps and parameter bindings, naive, marginal and projected costs, warm steps, freshness requirements, budget reductions, every candidate, the cold winner, and whether replanning changed the selection. Nothing about it is recomputed in the browser. [The planner: what the Plan stores](../architecture/planner.md#what-the-plan-stores)
- **Plan Inspector**: The console view of a stored plan, at `/app/plans/:id`: the cold winner beside the marginal winner, then every candidate with its costs and rejection reason. [The reference demo: seeing it in the UI](demo.md#seeing-it-in-the-ui)
- **Planner stages**: The four steps from an intent to a candidate set: A, retrieve (the top 8 engines by capability affinity and embedding similarity, plus substitutes and upstream producers); B, select (choose engines, and record why each rejected one lost); C, synthesize (dates, locale, entities, bindings, freshness); D, path-find (valid chains, and several candidate plans). [The planner](../architecture/planner.md)
- **Principal**: Who a request runs as, resolved from an API key or a JWT: organization, project, role, permissions, key environment, and any service session and its cap. It is cached in Redis for 60 seconds, and invalidated at once on rotation or revocation. [API keys: resolution](../security/api-keys.md#resolution)
- **Project**: A unit of work inside an organization, with its own API keys, optional upstream credential, engine policy, budgets, cache partition and execution mode. [Architecture overview: tenancy](../architecture/overview.md#tenancy)
- **Project execution mode**: `projects.execution_mode` (migration `0004`), a project's own default mode: `live`, `record` or `replay`. `NULL` inherits `SERPFLOW_MODE`, and changing it needs `project:write`. [Execution modes: setting it](execution-modes.md#setting-it) · [Migrations: 0004_project_mode](../database/migrations.md#0004_project_mode)
- **Projection**: `projected_full_scale_cost`, the uncapped cost of a plan's full shape: 101 credits for the reference chain. It is displayed and labelled as a projection, and never executed live. [Marginal-cost replanning: projections are never executed](../architecture/marginal-replanning.md#projections-are-never-executed)
- **Provenance headers**: The `X-SerpFlow-*` headers that say where a response came from: cache layer, matched query, entry age, TTL source, budget remaining, run, trace, catalog version and mode. `X-SerpFlow-Mode` is always present. [API overview: provenance headers](../api/overview.md#provenance-headers)

## Q

- **Query adapter**: A per-engine rewrite of the root-bound query, applied during parameter binding ([`text.py`](../../backend/app/core/text.py), [`planner/service.py`](../../backend/app/services/planner/service.py)). Google Finance is the one today: it gets a ticker, not a sentence, so "what is nvidia trading at right now" sends `q=NVDA:NASDAQ`. An explicit symbol in the intent wins, then a known company, index or crypto name, then the intent stripped of conversational filler. [The planner: query adapters](../architecture/planner.md#query-adapters)

## R

- **Rate limit**: 240 requests a minute per principal and path by default (`RATE_LIMIT_PER_MINUTE`), counted in Redis. It fails open if Redis is down; budgets, session caps and upstream quota are still enforced in PostgreSQL. [API overview: rate limiting](../api/overview.md#rate-limiting)
- **Readiness and liveness**: `/healthz` says the process is up and touches no dependency. `/readyz` checks PostgreSQL, Redis, Kafka, object storage and the catalog, and returns 503 only when PostgreSQL is unreachable. [Observability: health](../operations/observability.md#health)
- **Redaction filter**: `CredentialRedactionFilter`, on the root logger. It scrubs key-shaped values and sensitive `key=value` pairs from the message, the args, `extra=` attributes and the exception path. [Upstream credentials: never in a log](../security/credentials.md#never-in-a-log)
- **Reference demo**: `make demo`: three phases on the intent "find coordinated review rings among Koramangala cafes", proving that cache state changed the selected plan. It prints `PROVEN` and exits 0 only if it did, and spends zero credits. [The reference demo](demo.md)
- **Regional penalty**: The deterministic selector's 4.0-point deduction for an engine that serves one market (Naver for `kr`, Baidu for `cn`, Yandex and Yandex Images for `ru`, `by` and `kz`) when the intent resolves elsewhere. It is lifted when the intent names the engine or is written in that market's script. A rejected engine's recorded reason shows its lowered score, not the penalty ([`mock.py`](../../backend/app/integrations/llm/mock.py)). [The planner: stage B](../architecture/planner.md#stage-b-select)
- **Replay a run**: `POST /v1/runs/{id}/replay`, or `serpflow replay`: re-plans a recorded run's intent against today's cache state. It is unrelated to the `replay` execution mode. [API overview: runs](../api/overview.md#runs)
- **Retention**: The expiry a run is stamped with, as `expires_at`: 30 days by default, 7 days for a run that touched a `high` PII engine, both set instance-wide (`RETENTION_STANDARD_DAYS`, `RETENTION_HIGH_PII_DAYS`). Nothing purges expired runs or payloads automatically yet ([security policy: retention](../../SECURITY.md#retention)). [The executor: retention](../architecture/executor.md#retention)
- **Role**: The set of permissions a membership or API key holds. Five are built in: `owner`, `admin`, `developer`, `analyst` (plans and reads, never executes) and `service` (a narrow machine scope, defined apart from the human ladder). [API keys: roles](../security/api-keys.md#roles)
- **Routing accuracy**: The benchmark's headline figure: the share of 120 labelled tasks on which the planner chose the exact engine chain (or a declared alternative) and the right locale parameters. The deterministic adapter scores 38.3% on catalog v1.0.0. [Routing benchmark: scoring](benchmark.md#scoring)
- **Row-level security**: The PostgreSQL backstop for tenant isolation: 24 tables carry a policy keyed on `app.current_org`, which is set per transaction with `SET LOCAL` once the principal resolves. A table owner bypasses it, so production connects as a role that does not own the tables. [Row-level security](../database/rls.md)
- **Run**: One execution of a plan, identified as `run_...`, with its status, mode, credits spent and saved, provenance and steps. [Database schema: planning and execution](../database/schema.md#planning-and-execution)
- **Run Inspector**: The console view of a run, at `/app/runs/:id`: per step, the cache layer, the matched query and similarity, entry age, TTL source, credits and latency. A false hit is reported from here. [The reference demo: seeing it in the UI](demo.md#seeing-it-in-the-ui)

## S

- **SDKs**: The Python and TypeScript client libraries in this repository, thin HTTP clients over the API. They are not released yet, by the author's decision: they will be published to npm and PyPI when the author decides to host SerpFlow. Until then, a self-hosted instance installs them from a checkout and uses them on its own infrastructure. [SDKs overview](../sdks/overview.md) · [why they are not released](../sdks/releasing.md#first-who-runs-the-server)
- **Searches Archive**: SerpApi's archive of past searches, and SerpFlow's third cache layer. Re-reading an archived search by its `search_id` costs no credit, so the executor checks `archive_refs` before paying for a live call. [Caching: the Searches Archive](../architecture/caching.md#the-searches-archive)
- **Self-hosted**: How SerpFlow runs today, by the author's decision: you run your own instance, with its own PostgreSQL, Redis and Kafka and your own upstream keys. There is no public hosted instance; the author will host one once enough people ask in a GitHub issue. [Hosting](../../README.md#hosting) · [Installation](../deployment/installation.md)
- **Semantic layer**: The second cache layer: a pgvector similarity search over earlier queries in the same partition, accepted only at or above the project's similarity threshold (0.95 by default) and only if the entity and numeral guard agrees. Requests addressed purely by an opaque identifier skip it. The default embedder is local and deterministic: feature hashing into 384 dimensions. [Caching: threshold, and what the local embedder means for it](../architecture/caching.md#threshold-and-what-the-local-embedder-means-for-it)
- **SerpApi drop-in**: `SerpApiCompat`, in both SDKs: SerpApi's call shape, a params dict in and `get_dict()` / `getJson()` out. It sends `q` as the intent of a `POST /v1/search`, so SerpFlow's planner picks the engines; `engine` and the other parameters are only echoed back. [Python SDK: the SerpApi drop-in](../sdks/python.md#the-serpapi-drop-in)
- **Service session**: The identity a machine caller, such as an MCP agent, runs under: a `service_sessions` row with its own `session_cap` and `credits_used`. `SERPFLOW_MCP_SESSION` names it, so the MCP server resumes the same session across calls and restarts; without it, each call opens a fresh one. [API keys: service principal sessions](../security/api-keys.md#service-principal-sessions) · [MCP server: sessions and budgets](../sdks/mcp.md#sessions-and-budgets)
- **Session cap**: A service session's credit limit (20 for the seeded `service` key). Reaching it fails the call with `SESSION_CAP_EXCEEDED`, not the organization's `BUDGET_EXHAUSTED`. It bounds an agent's total only when the session is resumed by name. [MCP server: sessions and budgets](../sdks/mcp.md#sessions-and-budgets)
- **Single-candidate reason**: What a plan records when only one answering candidate exists: the engine's `single_source_note`, that no engine shares its capability tag, or that its substitutes are unreachable from this intent's parameters. [The planner: candidate plurality](../architecture/planner.md#candidate-plurality-is-a-hard-requirement)
- **SSE frame**: One Server-Sent Event on `GET /v1/runs/{id}/stream`, of type `stage`, `complete`, `error` or `heartbeat` (sent after 15 seconds of silence), carrying `stage`, `status`, `elapsed_ms`, `detail` and a `sequence`. The server keeps the last 400 frames per run for 15 minutes, so a client resumes with `Last-Event-ID`. [Streaming: frame shape](../api/streaming.md#frame-shape)
- **SSE stage**: One of the eleven real backend stage transitions a run streams, from `analyzing_intent` to `executing`, followed by `complete`. The console pipeline reveals them one at a time and never ahead of the real frame. [Streaming: the stage sequence](../api/streaming.md#the-stage-sequence) · [Frontend: the pipeline animation](../architecture/frontend.md#the-pipeline-animation)
- **Step**: One engine in a plan, with its parameters, dependencies and fan-out; at run time, a row recording the cache layer, credits, latency, mode and payload reference. [The executor: per-step record](../architecture/executor.md#per-step-record)
- **Substitute edge**: A link between two engines that serve the same capability, declared under `substitutes` with a coverage level and a user-facing trade-off note, or implied by a shared capability tag. Substitute edges are how engines compete: without them there is one candidate and nothing to re-rank. Catalog v1.0.0 has 69. [The engine catalog: both relationship kinds are mandatory](../architecture/catalog.md#both-relationship-kinds-are-mandatory)

## T

- **Test key**: An `sf_test_...` API key. It always routes to the deterministic mock, whatever any mode setting says: no upstream credential, zero credits, deterministic results. [API keys: test keys](../security/api-keys.md#test-keys)
- **Thesis**: SerpFlow's one claim: cache state should change which plan is selected, not just make the selected plan faster. `make demo` fails if it stops being true. [Product overview: the thesis](product-overview.md#the-thesis)
- **TTL source**: Why an entry has the TTL it has: `volatility_prior`, `learned`, `project_override` or `freshness_capped` (shortened to the step's freshness requirement). It is recorded on each step and returned in `X-SerpFlow-TTL-Source`. [Caching: adaptive TTL](../architecture/caching.md#adaptive-ttl)

## U

- **ULID**: The prefixed, time-sortable identifiers rows carry, such as `run_01M3WQ...`, `plan_...` and `key_...`. [Backend: identifiers](../architecture/backend.md#identifiers)
- **Upstream credential**: An organization's SerpApi or Groq key, envelope-encrypted in `upstream_credentials`. The SerpApi key resolves from the project, then the organization default, else `NO_UPSTREAM_CREDENTIAL`, and is decrypted only immediately before an upstream call: by the executor for a search, never in an API handler. [Upstream credentials](../security/credentials.md) · [The executor: the credential boundary](../architecture/executor.md#the-credential-boundary)
- **Upstream quota**: How many searches the SerpApi account itself has left, reconciled in the background into `upstream_quota_snapshots` and reported beside SerpFlow's budgets, never merged with them. A divergence between the two means the key is in use elsewhere. [Observability: execution and upstream](../operations/observability.md#execution-and-upstream)

## V

- **Volatility prior**: An engine's `volatility_prior` in the catalog, from `15m` to `365d`: how fast its results change. It seeds the adaptive TTL and is one of the signals for a step's freshness requirement. [The engine catalog: volatility and PII](../architecture/catalog.md#volatility-and-pii)

## W

- **Warm step**: A step whose result is already cached within its freshness requirement, so it costs nothing on the margin. For a fan-out step the probe counts warm calls, so 12 warm of 80 needed costs 68 credits. [Marginal-cost replanning: costing a step](../architecture/marginal-replanning.md#costing-a-step)

## Related

- [Product overview](product-overview.md): the thesis every term here exists to serve
- [Architecture overview](../architecture/overview.md#the-shape-of-a-request): where each mechanism sits in one request
- [API overview](../api/overview.md#errors): every error code these entries name, with its status and fix
- [Execution modes](execution-modes.md): the precedence behind live, record, replay and mock
- [SDKs and tools](../sdks/overview.md): the four surfaces that use this vocabulary from code
- [Troubleshooting](../operations/troubleshooting.md): what goes wrong with these mechanisms, and the fix

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Routing benchmark](../product/benchmark.md) | [Docs index](../README.md) · [Product index](../product/README.md) | [Deployment index](../deployment/README.md) |
