# Database schema

PostgreSQL 17 with `vector`, `pg_trgm` and `btree_gin`. 33 tables. All schema
changes go through Alembic; nothing is created by hand.

Models: [`backend/app/db/models/`](../../backend/app/db/models).

## Identity

```
organizations        name, slug, cache_scope, default_credential_id
users                email, Argon2id password_hash, verification + reset tokens
memberships          org_id + user_id -> role
projects             org_id, slug, key_prefix (unique), credential_id,
                     engine allow/denylist, semantic_threshold, ttl_overrides,
                     retention, shared_cache_enabled
project_members      optional per-project role override
auth_sessions        refresh token hash, rotation lineage, device, revocation
service_sessions     machine identity: api_key_id, session_cap, credits_used
```

`organizations.default_credential_id` and `upstream_credentials.org_id` form a
genuine cycle: an organization names a default credential, and every credential
belongs to an organization. The initial migration creates the table without the
forward reference and adds the constraint once both sides exist.

## Keys and credentials

```
api_keys                  project_prefix (indexed, plaintext), key_hash (HMAC),
                          display, role, is_service_principal, session_cap,
                          last_used_at, last_used_ip, rotation_grace_until
upstream_credentials      ciphertext, encrypted_dek, kek_id, algo, fingerprint,
                          validation_status, grace_until, upstream quota snapshot
upstream_quota_snapshots  periodic reconciliation, with divergence
```

The project prefix is stored in plaintext and uniquely indexed so a key is
identified with an index lookup rather than a scan over every key in the
system.

`upstream_credentials` has no column holding a recoverable plaintext key, and
no response schema in `app/schemas` has a field that could carry one.

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

`plan_candidates` exists because the Plan Inspector has to show why the
selected plan beat the alternatives, and `plans.marginal_replan_changed_selection`
is indexed so "show me the runs where replanning changed the answer" is a cheap
query.

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

The partition index comes first deliberately: semantic lookups filter on those
columns **before** any vector distance is computed. A full vector scan followed
by filtering would be slower and would cross the project isolation boundary
while doing it.

Guard material (`numerals`, `entities`, `versions`) is extracted once at write
time so a lookup does not re-derive it for every candidate row.

## Catalog projection

```
catalog_versions     version, counts, checksum
catalog_engines      the full spec plus an embedding and a search_text
catalog_edges        from_engine, to_engine, produces_field, satisfies_param,
                     fan_out_hint                     <- how engines CHAIN
catalog_substitutes  engine, substitute_engine, coverage, note, shared_tags
                                                      <- how engines COMPETE
```

A queryable projection of the committed YAML, loaded by `make seed`. The YAML
remains the source of truth.

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

`budget_ledger` carries both `project_id` and `beneficiary_project_id`. With a
shared organization cache the two differ, and keeping them apart is what makes
cross-project benefit a computed figure rather than an estimate:

```
SPEND     attributed to the project that fetched
SAVINGS   attributed to the project that benefited
```

`audit_log` is append-only at the database level, enforced by a trigger. See
[migrations](migrations.md).

## Benchmark

```
benchmark_tasks   the committed fixtures, loaded by make seed
benchmark_runs    per system per catalog_version, with by_category and
                  failure_modes
routing_evals     per task per run: predicted engines and params, correctness
                  flags, failure mode
```

Tracked per `catalog_version` so a routing regression is attributable to a
specific catalog change.

## Conventions

- **Identifiers** are prefixed ULIDs: `run_01M3WQ...`. Lexicographically
  sortable by creation time, readable in a log line.
- **Timestamps** are `TIMESTAMPTZ`, defaulting to `now()`, with `updated_at`
  maintained by `onupdate`.
- **Tenancy**: every scoped table carries `org_id` with an index, and appears
  in `RLS_TABLES` in the initial migration.
- **JSON columns** hold shapes that are read whole and never queried into:
  plan steps, cache state, stage traces, audit diffs.
- **Naming convention** is set on the metadata, so constraint names are stable
  and Alembic autogenerate produces clean diffs.

## Related

- [Migrations](migrations.md)
- [Row-level security](rls.md)
