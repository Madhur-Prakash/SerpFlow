# Threat model

What SerpFlow is trying to prevent, what it does about each thing, and what it
deliberately does not defend against.

SerpFlow is multi-tenant, holds other people's upstream API credentials, and
stores search results that can contain personal data. Those three facts set the
whole shape of this document.

## Assets

| Asset | Why it matters |
| --- | --- |
| Upstream SerpApi credentials | directly spendable money belonging to a customer |
| SerpFlow API keys | access to that spend, and to tenant data |
| Cached SERP payloads | may contain personal data (reviewer identities, profiles) |
| Run and plan history | reveals what an organization is researching |
| Audit log | the record everything else is checked against |

## Trust boundaries

```
browser / SDK / agent
        |  API key or bearer token
        v
 [ API layer ]  authn, authz, rate limit, tenant scoping
        |
        v
 [ services ]  planner, cache, executor      <- credential decrypts here only
        |
        v
 postgres (RLS)   redis   kafka   object storage
        |
        v
 SerpApi                                      <- the only outbound data path
```

Everything inside the service boundary is trusted with everything inside it.
The boundaries that are enforced are: caller to API, tenant to tenant, and
service to upstream.

## Threats and responses

### Cross-tenant data access

An authenticated caller for org A requests a run id belonging to org B.

Enforced twice. The application compares `org_id` on every resource fetched by
id; PostgreSQL row-level security on 23 tables is the backstop for a query that
forgets. The response is `404`, never `403` - confirming that an id exists in
another organization is itself a leak.

The cache is partitioned by project by default. A shared organization cache is
opt-in per project, and even then the partition key never spans organizations.

See [row-level security](../database/rls.md).

### Credential theft from the database

An attacker obtains a database dump.

Credentials are AES-256-GCM encrypted under a per-credential DEK which is
itself wrapped by a KEK that lives only in the process environment. The dump
contains ciphertext and wrapped DEKs. API key hashes are HMAC-SHA256 under a
server-side pepper, also not in the database, so a guessed key cannot be
verified offline either.

A dump alone is not enough. A dump **plus** the environment is, which is why
the production guidance puts the KEK in a KMS.

### Credential exfiltration through the API

Someone looks for an endpoint that returns the key they stored.

There is no such field. Not excluded, not redacted - absent from every response
model in `app/schemas`. A test walks the response models and asserts it,
because this is the rule most likely to be broken accidentally by a future
`model_dump()` or a convenience field on a subclass.

Decryption happens in three functions, all of which immediately make an
upstream call with the result.

### Credential leakage through logs

A secret reaches a log by more than one route: the message, the args, an
`extra=` attribute, or a traceback's local variables.

`CredentialRedactionFilter` covers all four and is tested on all four. Error
responses carry a code, a sentence and a request id - never a stack trace.

### Spend abuse

A compromised key, or an agent in a loop, burns the organization's SerpApi
quota.

Four independent limits:

- Budgets at organization, project, API key and session scope; the tightest
  applicable one wins.
- Service principal sessions have their own `session_cap`, so a machine caller
  is bounded as an identity rather than as a share of a human's key.
- Rate limiting per principal and path.
- Upstream quota is reconciled against SerpApi and reported separately.
  `BUDGET_EXHAUSTED` and `UPSTREAM_QUOTA_EXHAUSTED` are never conflated: they
  have different causes and different fixes.

### Stale or wrong cached data served as live

The cache is the product, so a bad hit is a correctness failure, not a
performance one.

- The deterministic entity/numeral/version guard runs **independently of the
  cosine score**. "Nvidia Q3 2024 revenue" and "Nvidia Q4 2024 revenue" embed
  close together and are rejected on exact set equality.
- Freshness bounds are enforced before reuse. A warm entry that does not meet
  the step's freshness requirement does not count as warm.
- `X-SerpFlow-Cache`, `X-SerpFlow-Age`, `X-SerpFlow-Matched-Query` and
  `X-SerpFlow-TTL-Source` are on every response, so provenance is never
  implicit.
- `X-SerpFlow-Mode` is always present. Replayed or mocked data is never
  presented as live.
- Operators can report a false hit from the Run Inspector, which invalidates
  the entry and increments a counter.

### Personal data in cached payloads

A `google_maps_contributor_reviews` payload is one named person's review
history across venues. That is not anonymous infrastructure data.

- Raw payload access sits behind its own permission, separate from run
  visibility.
- Steps carry a `pii_risk` level, and runs carry `max_pii_risk`.
- Retention is shorter for high-PII data: 7 days against 30.
- Payloads are content-addressed in object storage, not inlined into rows that
  are read casually.

### Tampering with the audit log

A compromised admin edits history to hide an action.

The audit log is append-only at the database level: a trigger refuses `UPDATE`
unconditionally and refuses `DELETE` unless the transaction has explicitly set
`app.audit_purge`, which only organization deletion does. Entries are hash
chained per organization, and `GET /v1/audit/verify` walks the chain and
reports the first break by sequence number.

Tampering is therefore both hard and detectable.

### Replay or mock data mistaken for live

A demo or a test run is read as a real result.

Mode precedence is absolute: a `test` API key routes to the deterministic mock
regardless of `SERPFLOW_MODE`, and this is not overridable by configuration.
Replay mode never silently falls back to the network - a cassette miss raises
`REPLAY_CASSETTE_MISS` rather than quietly spending a credit.

### Session theft

Refresh tokens are stored hashed with rotation lineage, so reuse of a rotated
token is detectable. Access tokens live 15 minutes. The SSE endpoint accepts a
short-lived access token as a query parameter because `EventSource` cannot set
headers - never an API key, never a refresh token, and nowhere else in the API.

### Denial of service

`MAX_REQUEST_BYTES` caps request size, rate limiting is per principal, and
planning is bounded by `PLANNER_MAX_CANDIDATES` and `PLANNER_MAX_HOPS` so a
pathological intent cannot make the graph search explode.

Rate limiting fails **open** if Redis is unavailable. That is a deliberate
choice: a cache outage taking down the API is a worse outcome than a brief
window without rate limits, given that every other limit - budgets, session
caps, upstream quota - is still enforced in PostgreSQL.

## Out of scope

Stated plainly, because an unstated boundary reads as an oversight:

- **A compromised host.** With the process environment, an attacker has the KEK
  and the pepper. Nothing in the application defends against that; it is what
  KMS and host hardening are for.
- **A malicious operator with database access and the environment.** Audit
  tampering is detectable, not preventable, against that adversary.
- **Upstream correctness.** SerpFlow caches and attributes what SerpApi
  returns. It does not verify it.
- **Side channels.** The HMAC comparison is constant-time. Cache timing as an
  oracle for whether another tenant has queried something is not defended
  against beyond partitioning.
- **Supply chain.** Dependencies are pinned through `uv.lock` and
  `package-lock.json`, which is pinning, not verification.

## Reporting

See [SECURITY.md](../../SECURITY.md).

## Related

- [Upstream credentials](credentials.md)
- [API keys](api-keys.md)
- [Secrets](secrets.md)
- [Row-level security](../database/rls.md)
