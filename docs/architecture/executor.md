# The executor

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="cache layers: exact · semantic · archive · live" src="https://img.shields.io/badge/cache%20layers-exact%20%C2%B7%20semantic%20%C2%B7%20archive%20%C2%B7%20live-2F6BFF">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="SerpApi: 54 engines" src="https://img.shields.io/badge/SerpApi-54%20engines-2F6BFF">
  <a href="../../backend/app/services/executor/service.py"><img alt="source: executor/service.py" src="https://img.shields.io/badge/source-executor%2Fservice.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **The executor** · page 15 of 50

Code: [`app/services/executor/service.py`](../../backend/app/services/executor/service.py)

**The executor runs the plan the planner selected.** Per step, it tries four layers in order:

```
EXACT  ->  SEMANTIC  ->  SEARCHES ARCHIVE  ->  LIVE
```

- **Only the last one spends a credit**

## The credential boundary

- **This is the one component allowed to decrypt an upstream SerpApi credential**
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
- More: [credentials](../security/credentials.md)

### Revocation mid-run

- **`_assert_credential_still_valid()` runs before every upstream call**, not once at the start
- If the credential was revoked mid-run and its grace window has closed, the run **fails loudly** with `CREDENTIAL_REVOKED`
- **It does not return the hops that happened to finish first**
  - a half-executed chain missing its final hop looks exactly like a complete answer
  - that is a worse outcome than an error

## Fan-out and binding

- **A step fed from upstream has no concrete values until the upstream step runs**
- `_resolve_bindings` extracts them from the real payload, using the dependency edge's field path:

```
google_maps.local_results[].data_id
  -> ["0x3bae14...", "0x3bae15...", ...]
  -> one google_maps_reviews call per value, capped at the step fan-out
```

- **No such value upstream?** The step fails with `BINDING_FAILED`, naming the field
  - instead of calling the engine with a missing parameter and getting a confusing upstream error
- **A fan-out step's responses are merged into one document**, list-valued keys concatenated, so downstream extraction sees the union

## Per-step record

Every step writes a row with what an operator needs to debug a route:

```
engine, parameters, depends_on, fan_out
status, cache_layer, matched_query, similarity, age_seconds, ttl_source
freshness_requirement, credits, latency_ms, confidence
payload_ref, payload_bytes, serpapi_search_id, http_status, mode, pii_risk
extracted                 the downstream-feeding fields, truncated
```

- `payload_ref` points at object storage
- **The payload itself sits behind `payload:read`**, a separate permission from run visibility

## Writing back

**On a live call**, the executor:

1. Records the spend against **every applicable budget scope**
2. Computes the TTL from the engine's volatility prior, **capped by the step's freshness requirement**
3. Stores the payload (content-addressed) and the durable cache entry, extracting the guard tokens **once, at write time**
4. Records an `archive_refs` row, so the Searches Archive can be reused later without paying again

**On a cache hit**, it records a **saving** instead:

- attributed by source: `exact`, `semantic`, `archive`
- with the **beneficiary project** kept separate from the fetching project, so cross-project benefit is computable

## Budget enforcement

- **Checked before every live call**, not once per run: a fan-out step can cross a threshold halfway through
- **The tightest applicable scope decides:**

```
session  ->  api_key  ->  project  ->  organization
```

- **Two different errors, never conflated:**

| Error | Means | Fix |
| --- | --- | --- |
| `BUDGET_EXHAUSTED` | your own cap is spent | raise your cap |
| `UPSTREAM_QUOTA_EXHAUSTED` | the SerpApi account is out | buy more upstream capacity |

## Engine policy

- **A denied engine is rejected during planning**, not mid-run, so the planner never proposes a path it cannot execute
- **The executor checks again anyway:** a policy can change between planning and execution

## Retention

- **A run inherits the highest `pii_risk`** of any engine it touched, and `expires_at` follows:
  - **7 days** for `high`
  - **30 days** otherwise
  - both configurable per project
- A `google_maps_contributor_reviews` payload is **one named person's complete review history** across venues
- **Cached SERPs are not anonymous infrastructure data**

## Related

- [Caching](caching.md): the four layers in detail
- [Credentials](../security/credentials.md): the decryption boundary
- [Execution modes](../product/execution-modes.md): live, record, replay, mock

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Caching](../architecture/caching.md) | [Docs index](../README.md) | [Backend](../architecture/backend.md) |
