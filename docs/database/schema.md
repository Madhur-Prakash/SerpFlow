# Database schema

<p>
  <a href="../README.md#database"><img alt="docs: Database" src="https://img.shields.io/badge/docs-Database-4169E1?logo=readthedocs&logoColor=white"></a>
  <img alt="tables: 33" src="https://img.shields.io/badge/tables-33-4169E1">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="SQLAlchemy: 2" src="https://img.shields.io/badge/SQLAlchemy-2-D71F00?logo=sqlalchemy&logoColor=white">
  <a href="../../backend/app/db/models"><img alt="source: db/models" src="https://img.shields.io/badge/source-db%2Fmodels-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Database](../README.md#database) › **Database schema** · page 22 of 50

- **PostgreSQL 17** with the `vector`, `pg_trgm` and `btree_gin` extensions
- **33 tables**
- **All schema changes go through Alembic.** Nothing is created by hand
- Models: [`backend/app/db/models/`](../../backend/app/db/models)

## Identity

```
organizations        name, slug, cache_scope, default_credential_id
users                email, Argon2id password_hash, verification + reset tokens
memberships          org_id + user_id -> role
projects             org_id, slug, key_prefix (unique), credential_id,
                     engine allow/denylist, semantic_threshold, ttl_overrides,
                     retention, shared_cache_enabled, execution_mode
project_members      optional per-project role override
custom_roles         org_id, name, slug (unique per org), description,
                     permissions[], created_by
auth_sessions        refresh token hash, rotation lineage, device, revocation
service_sessions     machine identity: api_key_id, session_cap, credits_used
```

- **A genuine foreign-key cycle:** `organizations.default_credential_id` → `upstream_credentials`, and `upstream_credentials.org_id` → `organizations`
  - an organization names a default credential; every credential belongs to an organization
  - the initial migration creates the table without the forward reference, then adds the constraint once both sides exist
- **`custom_roles`** (migration `0003`): organization-defined roles, each a named list of permissions from `GET /v1/roles/permissions`
- **`projects.execution_mode`** (migration `0004`): the project's own mode. `NULL` inherits `SERPFLOW_MODE`; a check constraint admits only `live`, `record` and `replay`. See [execution modes](../product/execution-modes.md)

## Keys and credentials

```
api_keys                  project_prefix (indexed, plaintext), key_hash (HMAC),
                          display, role, is_service_principal, session_cap,
                          last_used_at, last_used_ip, rotation_grace_until
upstream_credentials      ciphertext, encrypted_dek, kek_id, algo, fingerprint,
                          validation_status, grace_until, upstream quota snapshot
upstream_quota_snapshots  periodic reconciliation, with divergence
```

- **The project prefix is plaintext and uniquely indexed**, so a key is found with an index lookup, not a scan over every key
- **`upstream_credentials` has no column holding a recoverable plaintext key**
- **No response schema** in `app/schemas` has a field that could carry one

## Planning and execution

```
plans             intent, steps, parameter_bindings,
                  naive_cost, marginal_cost, projected_full_scale_cost,
                  warm_steps, freshness_requirements, budget_reduction,
                  confidence, catalog_version,
                  candidate_count, single_candidate_reason,
                  rejected_alternatives, rejected_engines,
                  selected_candidate_id, cold_winner_candidate_id,
                  marginal_replan_changed_selection, replan_explanation,
                  stage_trace

plan_candidates   EVERY candidate, not only the winner:
                  engines, steps, hops, naive_cost, marginal_cost,
                  warm_step_indices, cache_state, coverage, confidence,
                  naive_rank, marginal_rank, selected,
                  feasible_within_budget, rejection_reason, trade_off_note

runs              status, trigger, credits_spent, credits_saved,
                  cache_summary, provenance, mode, results_ref,
                  replay_of_run_id, expires_at, max_pii_risk

steps             engine, parameters, depends_on, fan_out, cache_layer,
                  matched_query, similarity, age_seconds, ttl_source,
                  freshness_requirement, credits, latency_ms,
                  payload_ref, serpapi_search_id, http_status, pii_risk
```

- **`plan_candidates` exists** because the Plan Inspector must show why the selected plan beat the alternatives. See [ADR 0014](../adr/0014-persist-every-candidate.md)
- **`plans.marginal_replan_changed_selection` is indexed**, so "show me the runs where replanning changed the answer" is a cheap query

## Cache

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

Indexes that matter:

```sql
ix_cache_entries_exact      (partition_key, request_hash) UNIQUE
ix_cache_entries_partition  (partition_key, engine, gl, hl, location)
ix_cache_entries_embedding_hnsw
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)
ix_cache_entries_query_trgm USING gin (query_text gin_trgm_ops)
```

- **The partition index comes first, deliberately:** semantic lookups filter on those columns **before** any vector distance is computed
  - a full vector scan then filtering would be slower, **and** cross the project isolation boundary
- **Guard material** (`numerals`, `entities`, `versions`) is extracted **once, at write time**, so a lookup does not re-derive it per candidate row

## Catalog projection

```
catalog_versions     version, counts, checksum
catalog_engines      the full spec plus an embedding and a search_text
catalog_edges        from_engine, to_engine, produces_field, satisfies_param,
                     fan_out_hint                     <- how engines CHAIN
catalog_substitutes  engine, substitute_engine, coverage, note, shared_tags
                                                      <- how engines COMPETE
```

- **A queryable projection of the committed YAML**, loaded by `make seed`
- **The YAML remains the source of truth.** See [catalog](../architecture/catalog.md)

## Governance

```
budgets                scope (organization|project|api_key|session), scope_id,
                       limit_credits, current_usage, period, alert_at,
                       on_exhausted
budget_ledger          kind (spend|saving), source (live|exact|semantic|
                       archive|routing), project_id, beneficiary_project_id
audit_log              sequence, actor, action, before, after, prev_hash,
                       entry_hash
alerts                 kind, severity, status, dedupe_key
notification_channels  email | webhook | slack, events, secret_hash
webhook_deliveries     attempts, response_status, delivered_at
```

- **`budget_ledger` carries both `project_id` and `beneficiary_project_id`**
  - with a shared organization cache the two differ
  - keeping them apart makes cross-project benefit a **computed figure**, not an estimate:

```
SPEND     attributed to the project that fetched
SAVINGS   attributed to the project that benefited
```

- **`audit_log` is append-only at the database level**, enforced by a trigger. See [migrations](migrations.md) and [ADR 0012](../adr/0012-append-only-audit-log.md)

## Benchmark

```
benchmark_tasks   the committed fixtures, loaded by make seed
benchmark_runs    per system per catalog_version, with by_category and
                  failure_modes
routing_evals     per task per run: predicted engines and params, correctness
                  flags, failure mode
```

- **Tracked per `catalog_version`**, so a routing regression is attributable to a specific catalog change. See [benchmark](../product/benchmark.md)

## Conventions

| Convention | Rule |
| --- | --- |
| **Identifiers** | prefixed ULIDs (`run_01M3WQ...`): sortable by creation time, readable in a log line |
| **Timestamps** | `TIMESTAMPTZ`, defaulting to `now()`; `updated_at` maintained by `onupdate` |
| **Tenancy** | every scoped table carries an indexed `org_id`, and has a row-level security policy |
| **JSON columns** | only for shapes read whole and never queried into: plan steps, cache state, stage traces, audit diffs |
| **Naming** | a naming convention on the metadata keeps constraint names stable, so Alembic autogenerate produces clean diffs |

## Related

- [Migrations](migrations.md)
- [Row-level security](rls.md)
- [Backend](../architecture/backend.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Worked examples](../api/examples.md) | [Docs index](../README.md) | [Migrations](../database/migrations.md) |
