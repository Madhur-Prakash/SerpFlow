# Database schema

<p>
  <a href="../README.md#database"><img alt="docs: Database" src="https://img.shields.io/badge/docs-Database-4169E1?logo=readthedocs&logoColor=white"></a>
  <img alt="tables: 33" src="https://img.shields.io/badge/tables-33-4169E1">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="SQLAlchemy: 2" src="https://img.shields.io/badge/SQLAlchemy-2-D71F00?logo=sqlalchemy&logoColor=white">
  <a href="../../docker/postgres/init/01-extensions.sql"><img alt="source: init/01-extensions.sql" src="https://img.shields.io/badge/source-init%2F01--extensions.sql-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 14 min" src="https://img.shields.io/badge/read-14%20min-555555">
</p>

[Docs](../README.md) › [Database](../README.md#database) › **Database schema** · page 29 of 57

- **PostgreSQL 17** with the `vector`, `pg_trgm` and `btree_gin` extensions
  - `vector` and `pg_trgm` are created by migration [`0001_initial`](migrations.md#0001_initial) and by the container's init script
  - `btree_gin` is created only by [`docker/postgres/init/01-extensions.sql`](../../docker/postgres/init/01-extensions.sql); no migration depends on it
- **33 tables**: 32 from `0001_initial`, plus `custom_roles` from `0003_custom_roles`. The chain: [migrations](migrations.md#the-revision-chain)
- **24 of them carry a row-level security policy**: every tenant-scoped table, plus `organizations`. The 9 without one are `users`, `auth_sessions`, the four catalog tables and the three benchmark tables. See [row-level security](rls.md#covered-tables)
- **All schema changes go through Alembic.** Nothing is created by hand
- Models: [`backend/app/db/models/`](../../backend/app/db/models) · identifiers, timestamps and the naming convention: [`app/db/base.py`](../../backend/app/db/base.py)
- **Every table below has its own heading**, so `schema.md#cache_entries` (or any other table name) links straight to it

## Identity

Behaviour: [API keys and roles](../security/api-keys.md), [execution modes](../product/execution-modes.md), [caching: partitioning](../architecture/caching.md#partitioning)

```
organizations        name, slug (unique), plan_tier, cache_scope,
                     default_credential_id, settings_json, deleted_at
users                email (unique), Argon2id password_hash,
                     verification + reset token hashes
memberships          org_id + user_id (unique) -> role
projects             org_id, slug (unique per org), key_prefix (unique),
                     credential_id, engine allow/denylist, semantic_threshold,
                     ttl_overrides, retention_days, retention_high_pii_days,
                     shared_cache_enabled, execution_mode, archived_at
project_members      optional per-project role override
custom_roles         org_id, name, slug (unique per org), description,
                     permissions[], created_by
auth_sessions        refresh token hash, rotation lineage, device, revocation
service_sessions     machine identity: api_key_id, external_session_ref,
                     session_cap, credits_used, runs_count, closed_at
```

### `organizations`

- **A genuine foreign-key cycle:** `organizations.default_credential_id` → `upstream_credentials`, and `upstream_credentials.org_id` → `organizations`
  - an organization names a default credential; every credential belongs to an organization
  - the initial migration creates the table without the forward reference, then adds the constraint once both sides exist ([migrations: 0001_initial](migrations.md#0001_initial))
- **`default_credential_id` is the SerpApi default**, second in the [credential resolution order](../security/byok.md#how-a-key-is-chosen-for-a-request)
- **`cache_scope` defaults to `project`.** A project reads and writes an organization-wide partition only when this is `organization` **and** the project sets `shared_cache_enabled` ([`_cache_scope`](../../backend/app/services/runs.py), [organization-level sharing](../architecture/caching.md#organization-level-sharing))
- **Its RLS policy keys on `id`**, not `org_id` ([row-level security](rls.md#covered-tables))

### `users`

- **Not tenant-scoped, and not under RLS:** a user can belong to several organizations, and `memberships` carries the tenancy
- **`password_hash` is Argon2id** ([ADR 0004](../adr/0004-hmac-for-api-keys.md#passwords-argon2id))
- **The verification and reset token columns hold HMAC-SHA256 hashes** under `API_KEY_PEPPER`, never the tokens themselves ([`hash_opaque_token`](../../backend/app/core/security.py)). The mail that carries them: [email](../operations/email.md#what-gets-sent)
- **`mfa_enabled` and `mfa_secret` exist as columns**; no endpoint sets them at HEAD

### `memberships`

- **Unique on `(org_id, user_id)`:** one role per user per organization
- **`role` holds a built-in role name or a custom role's slug**, checked against the organization when it is assigned ([API keys: roles](../security/api-keys.md#roles))

### `projects`

- **`key_prefix` is 6 plaintext characters, uniquely indexed** (`ix_projects_key_prefix`). Every API key issued for the project embeds it ([API keys: format](../security/api-keys.md#format))
- **`credential_id` is the project's own SerpApi credential**, first in the resolution order. `PATCH /v1/projects/{id}` refuses to point it at a non-SerpApi key ([bring your own key](../security/byok.md#how-a-key-is-chosen-for-a-request))
- **`projects.execution_mode`** (migration `0004`): the project's own mode. `NULL` inherits `SERPFLOW_MODE`; a check constraint admits only `live`, `record` and `replay`. See [execution modes](../product/execution-modes.md#who-chooses-and-precedence) and [ADR 0010](../adr/0010-test-key-mode-precedence.md#update-per-project-and-per-request-modes)
- **`engine_allowlist` / `engine_denylist`** are checked by the planner and again by the executor at each step ([executor: engine policy](../architecture/executor.md#engine-policy))
- **`retention_days` and `retention_high_pii_days` are stored, not applied:** the executor's retention deadline reads the instance settings ([executor: retention](../architecture/executor.md#retention))

### `project_members`

- **Unique on `(project_id, user_id)`.** When a row exists, its `role` replaces the organization role for requests scoped to that project ([`resolve_user_principal`](../../backend/app/services/auth/service.py))

### `custom_roles`

- **Added by migration `0003`**: organization-defined roles, each a named list of permissions from `GET /v1/roles/permissions`
- **Unique on `(org_id, slug)`**, and `slug` is indexed: a membership or key stores the slug, not the id
- **Under RLS from the same migration**, so a role defined in one organization is invisible to another
- Behaviour: [API keys: custom roles](../security/api-keys.md#custom-roles)

### `auth_sessions`

- **One row per refresh token:** `refresh_token_hash` (HMAC under the pepper, indexed), `expires_at`, `revoked_at`, and `rotated_from`, the session it replaced
- **Keyed by `user_id`, not under RLS**
- Behaviour: [threat model: session theft](../security/threat-model.md#session-theft)

### `service_sessions`

- **The identity a machine caller runs under**, with its own `session_cap`, `credits_used` and `runs_count`
- **`external_session_ref` (indexed) is the name in `SERPFLOW_MCP_SESSION`.** A call with the same name resumes the open session; a call without one opens a new row ([`open_service_session`](../../backend/app/services/auth/service.py))
- Behaviour: [API keys: service principal sessions](../security/api-keys.md#service-principal-sessions) · [MCP: sessions and budgets](../sdks/mcp.md#sessions-and-budgets)

## Keys and credentials

Behaviour: [API keys](../security/api-keys.md), [upstream credentials](../security/credentials.md), [bring your own key](../security/byok.md)

```
api_keys                  project_prefix (plaintext), environment, key_hash (HMAC),
                          display, role, is_service_principal, session_cap,
                          last_used_at, last_used_ip, use_count, expires_at,
                          revoked_at, rotated_from_id, rotation_grace_until
upstream_credentials      provider, project_id, ciphertext, encrypted_dek, kek_id,
                          algo, fingerprint, validation_status, grace_until,
                          revoked_at, upstream quota snapshot
upstream_quota_snapshots  periodic reconciliation, with divergence
```

### `api_keys`

- **Two indexes serve authentication:** `ix_api_keys_hash` on `key_hash` (unique) and `ix_api_keys_prefix_env` on `(project_prefix, environment)`. Resolution filters on all three, so a key is found with an index lookup, not a scan over every key ([API keys: resolution](../security/api-keys.md#resolution))
- **`project_prefix` copies the project's `key_prefix`.** Uniqueness lives on `projects.key_prefix`, since one project holds many keys
- **`key_hash` is HMAC-SHA256, not Argon2** ([ADR 0004](../adr/0004-hmac-for-api-keys.md))

### `upstream_credentials`

- **No column holds a recoverable plaintext key:** `ciphertext` and `encrypted_dek` are the two halves of the envelope ([ADR 0005](../adr/0005-envelope-encryption.md), [envelope encryption](../security/credentials.md#envelope-encryption))
- **No response schema** in `app/schemas` has a field that could carry one ([ADR 0006](../adr/0006-no-credential-field-in-schemas.md))
- **`provider` is `serpapi` or `groq`.** `project_id` NULL means an organization-wide credential; it is a plain column, not a foreign key
- **`fingerprint` is indexed**, so attaching a key the organization already holds is refused with `CONFLICT`. `ix_upstream_credentials_org_active` covers `(org_id, revoked_at)`

### `upstream_quota_snapshots`

- **One row per reconciliation** against SerpApi's account endpoint: `searches_left`, `internal_spend_since_last`, `upstream_spend_since_last`, and the `divergence` between the two
- **`raw` keeps the account response with its `api_key` field removed**
- Written by the `serpflow.quota.reconcile` consumer ([Kafka: topics](../operations/kafka.md#topics), [credentials: validation and revocation](../security/credentials.md#validation-and-revocation))

## Planning and execution

Behaviour: [planner](../architecture/planner.md), [marginal-cost replanning](../architecture/marginal-replanning.md), [executor](../architecture/executor.md)

```
plans             intent, normalized_intent, steps, parameter_bindings,
                  naive_cost, marginal_cost, projected_full_scale_cost,
                  warm_steps, freshness_requirements, budget_reduction,
                  confidence, catalog_version,
                  candidate_count, single_candidate_reason,
                  rejected_alternatives, rejected_engines,
                  selected_candidate_id, cold_winner_candidate_id,
                  marginal_replan_changed_selection, replan_explanation,
                  budget_limit, planner_latency_ms, mode, stage_trace

plan_candidates   EVERY candidate, not only the winner:
                  label, strategy, engines, steps, hops,
                  naive_cost, marginal_cost,
                  warm_step_indices, cache_state, coverage, confidence,
                  naive_rank, marginal_rank, selected,
                  feasible_within_budget, rejection_reason, trade_off_note

runs              status, trigger, credits_spent, credits_saved,
                  cache_summary, provenance, mode, results_ref,
                  result_summary, error_code, error_message,
                  api_key_id, service_session_id, trace_id,
                  replay_of_run_id, expires_at, max_pii_risk

steps             engine, parameters, depends_on, fan_out, cache_layer,
                  matched_query, similarity, age_seconds, ttl_source,
                  freshness_requirement, credits, latency_ms,
                  payload_ref, serpapi_search_id, http_status, pii_risk
```

### `plans`

- **`plans.marginal_replan_changed_selection` is indexed** (`ix_plans_replan_changed`), so "show me the runs where replanning changed the answer" is a cheap query. `ix_plans_project_created` serves the per-project history
- **`selected_candidate_id` and `cold_winner_candidate_id`** point into `plan_candidates`; when they differ, marginal re-ranking changed the answer ([what `changed_selection` means](../architecture/marginal-replanning.md#what-changed_selection-means), [ADR 0001](../adr/0001-marginal-cost-replanning.md))
- **`single_candidate_reason` is required when `candidate_count` is 1** ([candidate plurality](../architecture/planner.md#candidate-plurality-is-a-hard-requirement))
- **`budget_reduction`** records what [budget-aware reduction](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking) dropped, with its impact note
- **`stage_trace`** records each planner stage, including the provider and model that chose the engines ([what the Plan stores](../architecture/planner.md#what-the-plan-stores))

### `plan_candidates`

- **`plan_candidates` exists** because the Plan Inspector must show why the selected plan beat the alternatives. See [ADR 0014](../adr/0014-persist-every-candidate.md)
- **`ix_plan_candidates_plan_rank`** on `(plan_id, marginal_rank)` returns a plan's candidates in ranked order
- **`naive_rank` and `marginal_rank` side by side** are the counterfactual, stored rather than recomputed in the frontend ([ranking](../architecture/marginal-replanning.md#ranking))

### `runs`

- **`ix_runs_project_created` and `ix_runs_status`** serve the run list and its status filter
- **`mode`** is the mode the run executed under ([execution modes](../product/execution-modes.md)); `trigger` says where it came from (`interactive`, `mcp`, `replay`, `background`)
- **`api_key_id` and `service_session_id`** attribute machine-originated runs to a key and a [service session](#service_sessions)
- **`error_code` and `error_message`** carry a failed run's reason
- **`expires_at` (indexed) is the retention deadline**: `RETENTION_HIGH_PII_DAYS` when `max_pii_risk` is `high`, `RETENTION_STANDARD_DAYS` otherwise. Nothing deletes a run at that deadline yet ([executor: retention](../architecture/executor.md#retention))

### `steps`

- **`ix_steps_run_index`** on `(run_id, index)`; `engine`, `cache_layer` and `serpapi_search_id` are indexed on their own
- **`cache_layer`** is `exact`, `semantic`, `archive`, `live` or `skipped`
- **One row per plan step**, with the provenance the Run Inspector shows ([executor: per-step record](../architecture/executor.md#per-step-record))

## Cache

Behaviour: [caching](../architecture/caching.md) ([ADR 0003](../adr/0003-deterministic-semantic-guard.md), [ADR 0009](../adr/0009-freshness-gates-warmth.md))

```
cache_entries              partition_key, engine, gl, hl, location,
                           request_hash, normalized_request, query_text,
                           embedding vector(384),
                           numerals, entities, versions,     <- guard material
                           payload_ref, payload_bytes, result_count,
                           top_results_digest, credits_cost,
                           ttl_seconds, ttl_source, expires_at,
                           hit_count, refresh_count, pii_risk, invalidated_at

archive_refs               search_id, engine, request_hash, reuse_count
ttl_observations           previous/new TTL, direction, churn, interval
semantic_guard_rejections  both queries, both token sets, similarity, reason
false_hit_reports          operator reports from the Run Inspector
```

### `cache_entries`

Indexes that matter:

```sql
ix_cache_entries_exact      (partition_key, request_hash) UNIQUE
ix_cache_entries_partition  (partition_key, engine, gl, hl, location)
ix_cache_entries_embedding_hnsw
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)
ix_cache_entries_query_trgm USING gin (query_text gin_trgm_ops)
ix_cache_entries_expiry     (expires_at)
ix_cache_entries_project_engine (project_id, engine)
```

- **The partition index comes first, deliberately:** semantic lookups filter on those columns **before** any vector distance is computed
  - a full vector scan then filtering would be slower, **and** cross the project isolation boundary
- **`partition_key` is `project:<id>` by default, `org:<id>` when sharing is on**; `project_id` is the project whose upstream spend produced the entry ([partitioning](../architecture/caching.md#partitioning))
- **Guard material** (`numerals`, `entities`, `versions`) is extracted **once, at write time**, so a lookup does not re-derive it per candidate row ([the entity and numeral guard](../architecture/caching.md#the-entity-and-numeral-guard))
- **`embedding` is `vector(384)`, fixed by the migration.** It matches the default `EMBEDDING_DIM`; changing that setting needs a new revision
- **This table, not Redis, is the source of truth** ([Redis: why none of it is authoritative](../operations/redis.md#why-none-of-it-is-authoritative))
- **`mode` records the mode that wrote the entry; lookups do not filter on it**, so a mock or replayed payload can serve a later live run in the same partition ([threat model: replay or mock data mistaken for live](../security/threat-model.md#replay-or-mock-data-mistaken-for-live))

### `archive_refs`

- **Pointers into SerpApi's Searches Archive:** re-reading an archived search costs no credit, so the executor checks here before paying for a live call ([the Searches Archive](../architecture/caching.md#the-searches-archive))
- **`ix_archive_refs_search_id` is unique**; `ix_archive_refs_lookup` covers `(partition_key, request_hash)`

### `ttl_observations`

- **The adaptive TTL learning signal**, per engine **and** query class (`ix_ttl_obs_engine_class`): a volatile query on a stable engine still gets a short TTL ([adaptive TTL](../architecture/caching.md#adaptive-ttl))

### `semantic_guard_rejections`

- **Every near-match the guard refused**, with both queries, both token sets, the similarity and the reason, indexed on `(engine, created_at)` ([rejections are evidence](../architecture/caching.md#rejections-are-evidence))

### `false_hit_reports`

- **Filed from the Run Inspector**, tied to a run (`run_id`, cascading) and optionally a step and cache entry; `invalidated_entry` records whether the report invalidated it
- **The producer behind `serpflow_semantic_false_hit_reports_total`** ([observability: cache metrics](../operations/observability.md#cache), [worked example](../api/examples.md#report-a-bad-semantic-hit))

## Catalog projection

Behaviour: [the engine catalog](../architecture/catalog.md) ([ADR 0002](../adr/0002-typed-catalog-edges.md))

```
catalog_versions     version (unique), engine/edge/substitute/tag counts,
                     checksum, is_active
catalog_engines      the full spec plus an embedding and a search_text
catalog_edges        from_engine, to_engine, produces_field, satisfies_param,
                     fan_out_hint                     <- how engines CHAIN
catalog_substitutes  engine, substitute_engine, coverage, note, shared_tags,
                     confidence_penalty               <- how engines COMPETE
```

- **A queryable projection of the committed YAML**, loaded by `make seed` and by the startup seed ([bootstrap](../operations/bootstrap.md#what-happens))
- **The YAML remains the source of truth.** See [catalog](../architecture/catalog.md#how-it-is-loaded)
- **Not tenant-scoped:** no `org_id`, no RLS. Every row is keyed by `catalog_version`

### `catalog_versions`

- **One row per loaded catalog version**, with its counts and checksum ([versioning](../architecture/catalog.md#versioning))

### `catalog_engines`

- **Unique on `(catalog_version, engine)`**
- **`ix_catalog_engines_search_trgm`**, a GIN trigram index on `search_text` created by `0001_initial`, backs the [Catalog Explorer](../architecture/catalog.md#catalog-explorer) search box

### `catalog_edges`

- **Typed dependency edges**, indexed on `(catalog_version, from_engine)` and `(catalog_version, to_engine)` so path-finding walks them in both directions ([stage D](../architecture/planner.md#stage-d-path-find-and-generate-candidates))

### `catalog_substitutes`

- **Competing engines for one capability**, indexed on `(catalog_version, engine)` and `(catalog_version, substitute_engine)`. `note` surfaces verbatim as a Plan Inspector rejection reason ([both relationship kinds are mandatory](../architecture/catalog.md#both-relationship-kinds-are-mandatory))

## Governance

Behaviour: [executor: budget enforcement](../architecture/executor.md#budget-enforcement), [row-level security: the audit log](rls.md#the-audit-log), [API: governance](../api/overview.md#governance)

```
budgets                scope (organization|project|api_key|session), scope_id,
                       limit_credits, current_usage, period, alert_at,
                       on_exhausted, enabled
budget_ledger          kind (spend|saving), source (live|exact|semantic|
                       archive|routing), project_id, beneficiary_project_id,
                       run_id, step_id, api_key_id, session_id, credits
audit_log              sequence, actor, action, resource, before, after,
                       prev_hash, entry_hash
alerts                 kind, severity, status, dedupe_key
notification_channels  email | webhook | slack, events, secret_hash
webhook_deliveries     attempts, response_status, delivered_at
```

### `budgets`

- **Unique on `(scope, scope_id, period)`**; `ix_budgets_org_scope` covers `(org_id, scope)`
- **`period`** is `daily`, `weekly`, `monthly` or `total`; `alert_at` defaults to 0.8; `on_exhausted` is `stale`, `error` or `queue`, stored but not yet acted on by the executor
- **Every applicable budget must have room**, checked narrowest scope first ([executor: budget enforcement](../architecture/executor.md#budget-enforcement)), and the tightest remaining allowance feeds [budget-aware reduction](../architecture/marginal-replanning.md#budget-aware-reduction-happens-before-ranking)
- **A service-principal key created with a `session_cap` also gets an `api_key` budget of the same size** ([`create_key`](../../backend/app/api/v1/organizations.py))

### `budget_ledger`

- **`budget_ledger` carries both `project_id` and `beneficiary_project_id`**
  - with a shared organization cache the two differ
  - keeping them apart makes cross-project benefit a **computed figure**, not an estimate:

```
SPEND     attributed to the project that fetched
SAVINGS   attributed to the project that benefited
```

- **A SerpApi "no results" answer is a spend row**, because SerpApi bills it ([executor: an empty answer is still a billed answer](../architecture/executor.md#an-empty-answer-is-still-a-billed-answer))
- **`ix_ledger_project_created` and `ix_ledger_org_created`** serve the spend and savings figures ([observability: spend and savings](../operations/observability.md#spend-and-savings), [writing back](../architecture/executor.md#writing-back))

### `audit_log`

- **`audit_log` is append-only at the database level**, enforced by a trigger. See [migrations](migrations.md#0002_audit_purge), [row-level security: the audit log](rls.md#the-audit-log) and [ADR 0012](../adr/0012-append-only-audit-log.md)
- **Hash-chained per organization:** `entry_hash` is SHA-256 over the previous hash, `sequence`, actor, action, resource, `before`, `after` and `created_at`, which the application sets itself so the hash is final before the INSERT ([`AuditService.record`](../../backend/app/services/audit/service.py))
- **`before` and `after` are redacted** with the same rules as the log sinks before they are hashed
- **Indexes:** `ix_audit_org_created`, `ix_audit_actor`, `ix_audit_resource`

### `alerts`

- **Written by the `serpflow.alerts` consumer**, deduplicated on `dedupe_key` while an alert is open; `ix_alerts_org_status` serves the open-alert list ([Kafka: topics](../operations/kafka.md#topics))

### `notification_channels`

- **`kind` is `email`, `webhook` or `slack`.** `secret_hash` is the channel secret's HMAC under `API_KEY_PEPPER`; that stored value is also the key that signs a webhook's `x-serpflow-signature` header ([`handle_webhook`](../../backend/app/workers/consumers/handlers.py), [secrets](../security/secrets.md#inventory))

### `webhook_deliveries`

- **One row per webhook delivery**, with `attempts`, `response_status`, `error` and `delivered_at`; indexed on `(channel_id, created_at)`

## Benchmark

Behaviour: [routing benchmark](../product/benchmark.md)

```
benchmark_tasks   the committed fixtures, loaded by make seed
benchmark_runs    per system per catalog_version, with by_category and
                  failure_modes
routing_evals     per task per run: predicted engines and params, correctness
                  flags, failure mode
```

- **Tracked per `catalog_version`**, so a routing regression is attributable to a specific catalog change. See [benchmark](../product/benchmark.md#if-you-change-the-catalog)
- **Not under RLS.** `benchmark_runs.org_id` is nullable and carries no foreign key

### `benchmark_tasks`

- **Unique on `(task_key, suite_version)`**, loaded from [`backend/fixtures/benchmark/`](../../backend/fixtures/benchmark) ([the task set](../product/benchmark.md#the-task-set))

### `benchmark_runs`

- **`system` is `serpflow`, `unaided_llm` or `embedding_only`**, with accuracy split by engine, parameters and freshness ([scoring](../product/benchmark.md#scoring))

### `routing_evals`

- **One row per task per run**, cascading from `benchmark_runs`; `failure_mode` is indexed, which is what the [failure analysis](../product/benchmark.md#failure-analysis) groups on

## Conventions

| Convention | Rule |
| --- | --- |
| **Identifiers** | prefixed ULIDs (`run_01M3WQ...`): sortable by creation time, readable in a log line. See [backend: identifiers](../architecture/backend.md#identifiers) |
| **Timestamps** | `TIMESTAMPTZ` with a `now()` server default; `created_at` indexed on every table; `updated_at` maintained by `onupdate` |
| **Tenancy** | every tenant-scoped table carries an indexed `org_id`, cascading from `organizations`, and has a [row-level security](rls.md) policy |
| **JSON columns** | `JSON`, not `JSONB`, and only for shapes read whole and never queried into: plan steps, cache state, stage traces, audit diffs |
| **Naming** | a naming convention on the metadata keeps constraint names stable, so Alembic autogenerate produces clean diffs ([autogenerate configuration](migrations.md#autogenerate-configuration)) |

## Related

- [Migrations](migrations.md): the revision chain that creates these 33 tables
- [Row-level security](rls.md): which 24 tables are tenant-isolated, and how
- [Backend](../architecture/backend.md#identifiers): prefixed ULIDs, and how sessions reach these tables
- [Caching](../architecture/caching.md): what `cache_entries` and its neighbours do on every lookup
- [Upstream credentials](../security/credentials.md): the envelope behind `upstream_credentials`
- [ADR 0014](../adr/0014-persist-every-candidate.md): why `plan_candidates` keeps the losers too
- [ADR 0012](../adr/0012-append-only-audit-log.md): why `audit_log` refuses `UPDATE`
- [Troubleshooting: `type "vector" does not exist`](../operations/troubleshooting.md#type-vector-does-not-exist): when the extension is missing

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Releasing the SDKs](../sdks/releasing.md) | [Docs index](../README.md) | [Migrations](../database/migrations.md) |
