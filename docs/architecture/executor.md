# The executor

[`app/services/executor/service.py`](../../backend/app/services/executor/service.py)

The executor runs the plan the planner selected. Per step it tries four layers
in order:

```
EXACT  ->  SEMANTIC  ->  SEARCHES ARCHIVE  ->  LIVE
```

Only the last one spends a credit.

## The credential boundary

This is the one component permitted to decrypt an upstream SerpApi credential.
The plaintext exists in a local variable inside `execute()` and nowhere else:

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

It is never returned, never logged, never attached to a model, and does not
appear as a field in any response schema. See
[credentials](../security/credentials.md).

### Revocation mid-run

`_assert_credential_still_valid()` runs before **every** upstream call, not
once at the start. If the credential was revoked while the run was in flight
and its grace window has closed, the run fails loudly with
`CREDENTIAL_REVOKED`.

It does not return the hops that happened to complete first. A half-executed
chain missing its final hop looks exactly like a complete answer, and that is a
worse outcome than an error.

## Fan-out and binding

A step whose parameters come from upstream has no concrete values until the
upstream step runs. `_resolve_bindings` extracts them from the real payload
using the dependency edge field path:

```
google_maps.local_results[].data_id
  -> ["0x3bae14...", "0x3bae15...", ...]
  -> one google_maps_reviews call per value, capped at the step fan-out
```

If the upstream payload contains no such value the step fails with
`BINDING_FAILED` naming the field, rather than calling the engine with a
missing parameter and getting a confusing upstream error.

A fan-out step responses are merged into one document, with list-valued keys
concatenated, so downstream extraction sees the union.

## Per-step record

Every step writes a row carrying what an operator needs to debug a route:

```
engine, parameters, depends_on, fan_out
status, cache_layer, matched_query, similarity, age_seconds, ttl_source
freshness_requirement, credits, latency_ms, confidence
payload_ref, payload_bytes, serpapi_search_id, http_status, mode, pii_risk
extracted                 the downstream-feeding fields, truncated
```

`payload_ref` points at object storage; the payload itself is behind the
`payload:read` permission, separately from run visibility.

## Writing back

On a live call the executor:

1. Records the spend against every applicable budget scope.
2. Computes the TTL from the engine volatility prior, capped by the step
   freshness requirement.
3. Stores the payload (content-addressed) and the durable cache entry, with the
   guard tokens extracted once at write time.
4. Records an `archive_refs` row so the Searches Archive can be reused later
   without paying again.

On a cache hit it records a **saving** instead, attributed by source
(`exact`, `semantic`, `archive`), with the beneficiary project separated from
the fetching project so cross-project benefit is computable.

## Budget enforcement

Checked before every live call, not once per run, because a fan-out step can
cross a threshold halfway through. The tightest applicable scope decides:

```
session  ->  api_key  ->  project  ->  organization
```

`BUDGET_EXHAUSTED` and `UPSTREAM_QUOTA_EXHAUSTED` are raised separately and
never conflated: one means raise your own cap, the other means buy more
upstream capacity.

## Engine policy

A denied engine is rejected during planning, not mid-run, so the planner never
proposes a path it is not allowed to execute. The executor checks again anyway,
because a policy can change between planning and execution.

## Retention

A run inherits the highest `pii_risk` of any engine it touched, and
`expires_at` follows: 7 days for `high`, 30 otherwise, both configurable per
project.

A `google_maps_contributor_reviews` payload is one named person complete
review history across venues. Cached SERPs are not anonymous infrastructure
data.
