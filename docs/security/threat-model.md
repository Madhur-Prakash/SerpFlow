# Threat model

<p>
  <a href="../README.md#security"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="Argon2id: passwords" src="https://img.shields.io/badge/Argon2id-passwords-6E40C9">
  <img alt="HMAC: SHA-256" src="https://img.shields.io/badge/HMAC-SHA--256-6E40C9">
  <img alt="AES: 256-GCM" src="https://img.shields.io/badge/AES-256--GCM-6E40C9">
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [Security](../README.md#security) › **Threat model** · page 25 of 50

What SerpFlow is trying to prevent, what it does about each threat, and what it **deliberately does not** defend against.

**Three facts set the shape of this document.** SerpFlow:

- is **multi-tenant**
- holds **other people's upstream API credentials**
- stores search results that can contain **personal data**

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

- **Inside the service boundary, everything is trusted with everything**
- **The enforced boundaries:** caller to API, tenant to tenant, and service to upstream

## Threats and responses

| Threat | Main defence | Section |
| --- | --- | --- |
| Cross-tenant access | app guards + RLS, `404` not `403` | [↓](#cross-tenant-data-access) |
| Database dump | envelope encryption, peppered HMAC; KEK and pepper not in the DB | [↓](#credential-theft-from-the-database) |
| Exfiltration via the API | credential fields absent from every schema, test-enforced | [↓](#credential-exfiltration-through-the-api) |
| Leakage via logs | redaction filter on four routes | [↓](#credential-leakage-through-logs) |
| Spend abuse | four independent limits | [↓](#spend-abuse) |
| Wrong data served as live | deterministic guard, freshness, provenance headers | [↓](#stale-or-wrong-cached-data-served-as-live) |
| Personal data | separate permission, `pii_risk`, shorter retention | [↓](#personal-data-in-cached-payloads) |
| Audit tampering | append-only trigger + hash chain | [↓](#tampering-with-the-audit-log) |
| Mock mistaken for live | absolute mode precedence, loud replay misses | [↓](#replay-or-mock-data-mistaken-for-live) |
| Session theft | hashed refresh tokens, 15-minute access tokens | [↓](#session-theft) |
| Denial of service | body cap, rate limit, bounded planning | [↓](#denial-of-service) |

### Cross-tenant data access

**Scenario:** an authenticated caller for org A requests a run id belonging to org B.

- **Enforced twice:**
  - the application compares `org_id` on every resource fetched by id
  - PostgreSQL row-level security on **24 tables** is the backstop for a query that forgets
- **The response is `404`, never `403`:** confirming that an id exists in another organization is itself a leak
- **The cache is partitioned by project by default**
  - a shared organization cache is opt-in per project
  - even then, the partition key **never spans organizations**
- More: [row-level security](../database/rls.md)

### Credential theft from the database

**Scenario:** an attacker obtains a database dump.

- **Credentials are AES-256-GCM encrypted** under a per-credential DEK, itself wrapped by a KEK that lives **only in the process environment**
  - the dump holds ciphertext and wrapped DEKs, nothing more
- **API key hashes are HMAC-SHA256 under a server-side pepper**, also not in the database
  - so a guessed key cannot be verified offline either
- **A dump alone is not enough. A dump plus the environment is**, which is why production guidance puts the KEK in a KMS

### Credential exfiltration through the API

**Scenario:** someone looks for an endpoint that returns the key they stored.

- **There is no such field.** Not excluded, not redacted: **absent** from every response model in `app/schemas`
- **A test walks the response models and asserts it**, because this rule is the one most likely to be broken by accident (a future `model_dump()`, or a convenience field on a subclass)
- **Decryption happens in three functions**, each of which immediately makes an upstream call with the result

### Credential leakage through logs

**A secret can reach a log four ways:** the message, the args, an `extra=` attribute, or a traceback's local variables.

- **`CredentialRedactionFilter` covers all four, and is tested on all four**
- **Error responses** carry a code, a sentence and a request id. Never a stack trace

### Spend abuse

**Scenario:** a compromised key, or an agent in a loop, burns the organization's SerpApi quota.

**Four independent limits:**

1. **Budgets** at organization, project, API key and session scope; the tightest applicable one wins
2. **Service principal sessions** have their own `session_cap`, so a machine caller is bounded **as an identity**, not as a share of a human's key
3. **Rate limiting** per principal and path
4. **Upstream quota** is reconciled against SerpApi and reported separately
   - `BUDGET_EXHAUSTED` and `UPSTREAM_QUOTA_EXHAUSTED` are never conflated: different causes, different fixes

### Stale or wrong cached data served as live

**The cache is the product**, so a bad hit is a **correctness** failure, not a performance one.

- **The deterministic entity, numeral and version guard runs independently of the cosine score**
  - "Nvidia Q3 2024 revenue" and "Nvidia Q4 2024 revenue" embed close together, and are rejected on exact set equality
- **Freshness bounds are enforced before reuse:** a warm entry that misses the step's freshness requirement does not count as warm
- **Provenance is never implicit:** `X-SerpFlow-Cache`, `X-SerpFlow-Age`, `X-SerpFlow-Matched-Query` and `X-SerpFlow-TTL-Source` are on every response
- **`X-SerpFlow-Mode` is always present.** Replayed or mocked data is never presented as live
- **Operators can report a false hit** from the Run Inspector: it invalidates the entry and increments a counter

### Personal data in cached payloads

**A `google_maps_contributor_reviews` payload is one named person's review history across venues.** That is not anonymous infrastructure data.

- **Raw payload access has its own permission**, separate from run visibility
- **Steps carry a `pii_risk` level**, and runs carry `max_pii_risk`
- **Retention is shorter for high-PII data:** 7 days against 30
- **Payloads are content-addressed in object storage**, not inlined into rows that are read casually

### Tampering with the audit log

**Scenario:** a compromised admin edits history to hide an action.

- **Append-only at the database level:**
  - a trigger refuses `UPDATE` unconditionally
  - it refuses `DELETE` unless the transaction set `app.audit_purge`, which only organization deletion does
- **Hash chained per organization:** `GET /v1/audit/verify` walks the chain and reports the first break, by sequence number
- **Tampering is therefore both hard and detectable**

### Replay or mock data mistaken for live

**Scenario:** a demo or test run is read as a real result.

- **Mode precedence is absolute:** a `test` API key routes to the deterministic mock regardless of `SERPFLOW_MODE`, and no configuration overrides it
- **Replay never silently falls back to the network:** a cassette miss raises `REPLAY_CASSETTE_MISS` instead of quietly spending a credit

### Session theft

- **Refresh tokens are stored hashed, with rotation lineage**, so reuse of a rotated token is detectable
- **Access tokens live 15 minutes**
- **The SSE endpoint accepts a short-lived access token as a query parameter**, because `EventSource` cannot set headers
  - never an API key, never a refresh token, and nowhere else in the API

### Denial of service

- **`MAX_REQUEST_BODY_BYTES`** caps request size (1 MiB by default)
- **Rate limiting** is per principal
- **Planning is bounded** by `PLANNER_MAX_CANDIDATES` and `PLANNER_MAX_HOPS`, so a pathological intent cannot make the graph search explode
- **Rate limiting fails open if Redis is unavailable.** A deliberate choice:
  - a cache outage taking down the API is worse than a brief window without rate limits
  - every other limit (budgets, session caps, upstream quota) is still enforced in PostgreSQL

## Out of scope

Stated plainly, because an unstated boundary reads as an oversight:

- **A compromised host.** With the process environment, an attacker has the KEK and the pepper. Nothing in the application defends against that; KMS and host hardening do
- **A malicious operator with database access and the environment.** Audit tampering is detectable, not preventable, against that adversary
- **Upstream correctness.** SerpFlow caches and attributes what SerpApi returns. It does not verify it
- **Side channels.** The HMAC comparison is constant-time. Cache timing as an oracle for "has another tenant queried this?" is not defended beyond partitioning
- **Supply chain**
  - the frontend is pinned by `package-lock.json`
  - Python dependencies are **lower-bounded in `pyproject.toml`, not locked**: there is no `uv.lock` yet, so a fresh install can resolve newer versions
  - pinning is not verification either way

## Reporting

- Report privately: [SECURITY.md](../../SECURITY.md)
- **Maintained by one person in their own time.** Response is best-effort: see [maintenance and support](../../SECURITY.md#maintenance-and-support)

## Related

- [Bring your own key](byok.md)
- [Upstream credentials](credentials.md)
- [API keys](api-keys.md)
- [Secrets](secrets.md)
- [Row-level security](../database/rls.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Row-level security](../database/rls.md) | [Docs index](../README.md) | [Bring your own key](../security/byok.md) |
