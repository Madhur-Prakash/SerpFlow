# The executor

<p>
  <a href="../architecture/README.md"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="cache layers: exact · semantic · archive · live" src="https://img.shields.io/badge/cache%20layers-exact%20%C2%B7%20semantic%20%C2%B7%20archive%20%C2%B7%20live-2F6BFF">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="SerpApi: 54 engines" src="https://img.shields.io/badge/SerpApi-54%20engines-2F6BFF">
  <a href="../../backend/app/services/executor/service.py"><img alt="source: executor/service.py" src="https://img.shields.io/badge/source-executor%2Fservice.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 12 min" src="https://img.shields.io/badge/read-12%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../architecture/README.md) › **The executor** · page 19 of 57

Code: [`app/services/executor/service.py`](../../backend/app/services/executor/service.py) · [`app/integrations/serpapi/`](../../backend/app/integrations/serpapi) · [`app/services/runs.py`](../../backend/app/services/runs.py)

**The executor runs the plan the [planner](planner.md) selected** after [marginal-cost replanning](marginal-replanning.md). Per step, it tries four [cache layers](caching.md) in order, through [`cache.lookup()`](caching.md#two-entry-points):

```
EXACT  ->  SEMANTIC  ->  SEARCHES ARCHIVE  ->  LIVE
```

- **Only the last one spends a credit**, and only in the `live` and `record` [execution modes](../product/execution-modes.md)
- **There is one way in:** `plan_and_execute` in [`app/services/runs.py`](../../backend/app/services/runs.py)
  - the REST API calls it, and the [CLI](../sdks/cli.md) and both [SDKs](../sdks/overview.md) reach it through the REST API; the [MCP server](../sdks/mcp.md) calls it in-process, and the [Kafka](../operations/kafka.md) worker calls it for background runs
  - interactive search runs on the request's own event loop, never through Kafka

## The credential boundary

- **This is the only place a SerpApi credential is decrypted to run a search.** Credential validation and quota reconciliation decrypt for one probe call each ([credentials: where it is decrypted](../security/credentials.md#where-it-is-decrypted))
- **The credential is resolved only when the mode needs one** (`live`, `record`): the project's own key, else the organization default, else `NO_UPSTREAM_CREDENTIAL` ([BYOK: how a key is chosen](../security/byok.md#how-a-key-is-chosen-for-a-request), [fix](../operations/troubleshooting.md#no_upstream_credential))
- The plaintext exists in a local variable inside `execute()`, and nowhere else:

```python
upstream_key = None
if self.mode.mode in ("live", "record"):
    upstream_key = self._decrypt_credential()
try:
    ...
finally:
    # Zero the local before it can be captured by a traceback frame.
    upstream_key = None
```

- It is **never** returned, logged, attached to a model, or present as a field in any response schema
- More: [credentials](../security/credentials.md), [envelope encryption](../adr/0003-envelope-encryption.md)

### Revocation mid-run

- **`_assert_credential_still_valid()` runs before every upstream call**, not once at the start
- If the credential was revoked mid-run and its grace window (`grace_until`) has closed, the run **fails loudly** with `CREDENTIAL_REVOKED` (409)
- **It does not return the hops that happened to finish first**
  - a half-executed chain missing its final hop looks exactly like a complete answer
  - that is a worse outcome than an error
- [Troubleshooting: `CREDENTIAL_REVOKED` part-way through a run](../operations/troubleshooting.md#credential_revoked-part-way-through-a-run)

## Where LIVE goes

Code: [`SerpApiGateway`](../../backend/app/integrations/serpapi/__init__.py)

- **Every upstream search leaves through one `SerpApiGateway`**, built once per run with the mode `resolve_execution_mode` resolved ([precedence](../product/execution-modes.md#who-chooses-and-precedence), [ADR 0005](../adr/0005-test-key-mode-precedence.md))
- **The archive is tried first, in `live` and `record` only:** an archived re-read is free. In `replay` and `mock` there is no archive to read

| Mode | What the LIVE layer does | Credited | Step `cache_layer` |
| --- | --- | :---: | --- |
| `live` | `SerpApiClient.search` against SerpApi | yes | `live` |
| `record` | the same, then writes a cassette if the response is not an error | yes | `live` |
| `replay` | loads the cassette; **never the network** | no | `live` |
| `mock` | the deterministic generator, reachable only with a `test` key | no | `mock` |

- **Each step and the run carry `mode`:** a replayed step is recorded as `cache_layer=live`, `mode=replay`, `credits=0`, so it is never mistaken for a live call
- **Cassettes** ([`cassettes.py`](../../backend/app/integrations/serpapi/cassettes.py)) live at `<CASSETTE_DIR>/<engine>/<key>.json` (default `./fixtures/cassettes`, set in [`.env.example`](../../.env.example))
  - the key is a BLAKE2b digest of the engine and the sorted parameters, minus `api_key`, `output`, `no_cache` and nulls
  - each file holds the engine, parameters, `recorded_at`, `http_status`, `latency_ms` and the payload
  - **a miss raises `REPLAY_CASSETTE_MISS` (503) naming the expected file**, instead of falling through to a live call ([fix](../operations/troubleshooting.md#replay_cassette_miss))
- **The mock** ([`mock.py`](../../backend/app/integrations/serpapi/mock.py)) seeds its generator from the engine plus the normalised parameters, so the same request always returns the same `data_id`s, reviews and `contributor_id`s, and chains work offline
  - every mock payload carries `search_metadata.serpflow_mock = true`

## Fan-out and binding

- **A step fed from upstream has no concrete values until the upstream step runs**
- `_resolve_bindings` extracts them from the real payload, using the [dependency edge](catalog.md#both-relationship-kinds-are-mandatory)'s field path:

```
google_maps.local_results[].data_id
  -> ["0x3bae14...", "0x3bae15...", ...]
  -> one google_maps_reviews call per value, capped at the step fan-out
```

- **No such value upstream?** The step fails with `BINDING_FAILED`, naming the field
  - instead of calling the engine with a missing parameter and getting a confusing upstream error
  - the same code covers an unbound placeholder, or an upstream step that produced no payload
- **Each call in a fan-out goes through the four layers on its own**, so one step can be partly warm
- **A fan-out step's responses are merged into one document**, list-valued keys concatenated, so downstream extraction sees the union

## Per-step record

Every step writes a row to [`steps`](../database/schema.md#planning-and-execution) with what an operator needs to debug a route:

```
engine, label, parameters, depends_on, fan_out
status, cache_layer, matched_query, similarity, age_seconds, ttl_source
freshness_requirement, credits, latency_ms, confidence
payload_ref, payload_bytes, serpapi_search_id, http_status, mode, pii_risk
error_code, error_message
extracted                 the downstream-feeding fields, first 20 values each
```

- **`parameters` holds the step's static parameters**, with `api_key`, `output` and `no_cache` stripped; values bound from upstream are not repeated
- **`cache_layer` is the layer that served the step's last call**, and the run's `cache_summary` counts all of the step's calls under it. For a partly warm fan-out, the ledger has the per-call truth: one spend or saving row per billed or cached call
- `payload_ref` points at [object storage](caching.md#object-storage): gzip JSON, content-addressed
- **The payload itself sits behind `payload:read`**, a separate permission from run visibility: [`GET /v1/runs/{id}/steps/{step_id}/payload`](../api/overview.md#runs)

## The run record

At the end, success or failure, the executor stamps the [`runs`](../database/schema.md#planning-and-execution) row:

```
status, mode, started_at, finished_at, duration_ms
credits_spent, credits_saved, naive_cost, marginal_cost
cache_summary             calls per layer: exact, semantic, archive, live, mock
result_summary            the terminal step's summary, plus notice
results_ref               the terminal step's payload_ref
max_pii_risk, expires_at
provenance                mode, mode_reason, catalog_version,
                          credential_fingerprint, layers, llm_provider
```

- **`credits_saved` is `cost x fan_out - credits` per step**, so a `replay` or `mock` run reports its whole naive cost as saved
  - the ledger is stricter: it records a saving only for an actual exact, semantic or archive hit, plus the routing saving
- **A synchronous search's response carries the same provenance** in `X-SerpFlow-*` headers: the dominant layer, the first step's matched query, age and TTL source, the budget remaining, the run id and the mode ([provenance headers](../api/overview.md#provenance-headers))
- `serpflow_run_duration_seconds{status}` and `serpflow_step_latency_seconds{engine, cache_layer}` time both levels ([metrics](../operations/observability.md#execution-and-upstream))

## Writing back

**On an upstream answer**, the executor:

1. **Records the spend, if the response was credited** (`live`, `record`):
   - a [`budget_ledger`](../database/schema.md#governance) row, `kind=spend`, `source=live`, attributed to the fetching project
   - the credits added to `current_usage` on **every applicable budget**, which can raise a `budget.threshold_reached` or `budget.exhausted` alert ([`budgets/service.py`](../../backend/app/services/budgets/service.py))
   - `serpflow_credits_spent_total` incremented ([spend and savings](../operations/observability.md#spend-and-savings))
2. Computes the TTL from the engine's volatility prior (or the project's per-engine TTL override), **capped by the step's freshness requirement** ([adaptive TTL](caching.md#adaptive-ttl))
3. Stores the payload (content-addressed) and the durable cache entry, extracting the [guard tokens](caching.md#the-entity-and-numeral-guard) **once, at write time**, and refreshes the [Redis](../operations/redis.md) hot entry
   - this happens in every mode; the entry records the mode it was written under
4. Records an `archive_refs` row with the credential fingerprint, when the mode is `live` or `record` and SerpApi returned a search id, so the [Searches Archive](caching.md#the-searches-archive) can be reused later without paying again

**On a cache hit**, it records a **saving** instead:

- one `kind=saving` ledger row per call, attributed by source: `exact`, `semantic`, `archive`
- with the **beneficiary project** kept separate from the fetching project, so cross-project benefit is computable ([organization-level sharing](caching.md#organization-level-sharing))

**After the run**, `plan_and_execute` adds the rest:

- a `routing` saving, when the plan ranked first on cold cost was passed over and costs more cold than the one selected
- the service session's `credits_used` and `runs_count`, for [session caps](../security/api-keys.md#service-principal-sessions)
- a `run.executed` row in the hash-chained [audit log](../database/rls.md#the-audit-log)

## An empty answer is still a billed answer

Code: [`SerpApiResponse.is_empty_result`](../../backend/app/integrations/serpapi/client.py)

- **SerpApi reports "no results" through the same `error` field it uses for failures** ("Google Finance hasn't returned any results for this query."), but the search was processed, and it is billed
- **`is_empty_result` is true** when the HTTP status is below 400, the payload has an `error`, and either `search_metadata.status` is `"Success"` or the message says the engine "hasn't returned any results"
- **Such a response is not `is_error`**, so the executor treats it as a successful live call:
  - the spend is recorded, in the ledger and against budgets
  - the payload is cached and archived like any other, and written to a cassette in `record`
  - **SerpApi's message becomes `summary.notice`** (at most 300 characters) when the terminal step's summary has no items, so the console says "SerpApi found no results" instead of showing a broken run ([frontend](frontend.md#the-pipeline-animation))
- **Before this, the step failed and the ledger recorded 0 credits** for a search SerpApi had charged for
- A downstream step that needed values from the empty payload still fails with `BINDING_FAILED`

## Upstream failures

Code: [`SerpApiClient`](../../backend/app/integrations/serpapi/client.py)

| SerpApi answer | Outcome | Code | Status |
| --- | --- | --- | ---: |
| HTTP 401 | run fails | `CREDENTIAL_REJECTED` | 502 |
| HTTP 429, or an `error` saying the account ran out | run fails | `UPSTREAM_QUOTA_EXHAUSTED` | 402 |
| any other 4xx/5xx, or an `error` that is not an empty result | step and run fail; `serpflow_upstream_errors_total` incremented | `UPSTREAM_ERROR` | 502 |
| timeout or network error | retried, 3 attempts with exponential backoff, then fails | `UPSTREAM_ERROR` | 502 |
| a binding with no value | step and run fail | `BINDING_FAILED` | 502 |
| an empty result | success, billed | | |

- **A 4xx is never retried:** a bad request is not transient
- **A failed archive read falls through to live**, logged as `archive.miss`
- Codes and remedies: [API errors](../api/overview.md#errors), [troubleshooting](../operations/troubleshooting.md#execution)

## When a run fails

- **A step that fails on its own (`UPSTREAM_ERROR`, `BINDING_FAILED`) records `status=failed`, `error_code` and `error_message`**, with `details` naming the step and engine
- **Whatever the error, the executor stamps the run `failed`** with its code and message, and re-raises it to the caller
- **The request's transaction is then rolled back** ([`get_session`](../../backend/app/api/deps.py), [backend: request lifecycle](backend.md#request-lifecycle)), so the plan, step rows, ledger entries and cache writes from that run are not persisted
  - **synchronous `POST /v1/search`:** the run row goes with them; the caller has the error envelope and its `request_id`
  - **streamed search:** the run row was committed as `pending` before the 202 went back, and [`_execute_detached`](../../backend/app/api/v1/search.py) marks it `failed` with the code and message in a fresh transaction. The Run Inspector shows why it failed, but its `credits_spent` reads 0 and it has no plan and no steps, even if an earlier step made a billed call
- **SerpApi's account still counts any search it processed.** Quota reconciliation reports the gap between the ledger and the account as `serpflow_upstream_quota_divergence`

## Budget enforcement

- **Checked before every call that reaches the gateway**, not once per run: a fan-out step can cross a threshold halfway through
  - the check runs whatever the mode, so a `replay` or test-key run against an exhausted budget is refused too
- **Every applicable budget must have room.** They are checked narrowest first, and the first that cannot afford the call is the one reported (`details.binding_scope`):

```
session  ->  api_key  ->  project  ->  organization
```

- **Before execution**, the tightest remaining allowance has already fed [budget-aware reduction](marginal-replanning.md#budget-aware-reduction-happens-before-ranking) in the planner
- **A budget's `on_exhausted` (`stale`, `error`, `queue`) is stored and returned in `details`**, but the executor raises `BUDGET_EXHAUSTED` whatever it says
- **Two different errors, never conflated:**

| Error | Means | Fix |
| --- | --- | --- |
| `BUDGET_EXHAUSTED` | your own cap is spent | raise your cap |
| `UPSTREAM_QUOTA_EXHAUSTED` | the SerpApi account is out | buy more upstream capacity |

- [Troubleshooting: `BUDGET_EXHAUSTED` against `UPSTREAM_QUOTA_EXHAUSTED`](../operations/troubleshooting.md#budget_exhausted-against-upstream_quota_exhausted)

## Engine policy

- **A denied engine is rejected during planning**, not mid-run, so the planner never proposes a path it cannot execute
- **The executor checks again anyway**, at the start of each step: a policy can change between planning and execution
- A step outside the project's allowlist, or on its denylist, fails the run with `ENGINE_NOT_ALLOWED` (403)

## Retention

- **A run inherits the highest `pii_risk`** of any engine in its plan, and `expires_at` follows:
  - **7 days** for `high`
  - **30 days** otherwise
  - set instance-wide by `RETENTION_HIGH_PII_DAYS` and `RETENTION_STANDARD_DAYS` ([production: retention](../deployment/production.md#retention))
- **Projects carry `retention_days` and `retention_high_pii_days`**, settable through `PATCH /v1/projects/{id}`, but the executor does not read them yet: the instance values decide
- **Nothing deletes a run at its `expires_at` yet.** The deadline is recorded and returned on the run, not enforced
- A `google_maps_contributor_reviews` payload is **one named person's complete review history** across venues
- **Cached SERPs are not anonymous infrastructure data** ([threat model: personal data in cached payloads](../security/threat-model.md#personal-data-in-cached-payloads))

## Related

- [Caching](caching.md): the four layers, `lookup()`, the guard and adaptive TTL in detail
- [Marginal-cost replanning](marginal-replanning.md): how the plan the executor runs was chosen, and the budget reduction before it
- [Execution modes](../product/execution-modes.md): live, record, replay and mock, and who chooses
- [Credentials](../security/credentials.md): the decryption boundary and revocation
- [Database schema](../database/schema.md#governance): `runs`, `steps`, `budgets` and `budget_ledger`
- [Streaming](../api/streaming.md): the `executing` frames each step publishes
- [Troubleshooting: execution](../operations/troubleshooting.md#execution): cassette misses, budget errors, revoked credentials

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Caching](../architecture/caching.md) | [Docs index](../README.md) · [Architecture index](../architecture/README.md) | [Backend](../architecture/backend.md) |
