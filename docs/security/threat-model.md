# Threat model

<p>
  <a href="../README.md#security"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="Argon2id: passwords" src="https://img.shields.io/badge/Argon2id-passwords-6E40C9">
  <img alt="HMAC: SHA-256" src="https://img.shields.io/badge/HMAC-SHA--256-6E40C9">
  <img alt="AES: 256-GCM" src="https://img.shields.io/badge/AES-256--GCM-6E40C9">
  <a href="../../backend/app/api/middleware.py"><img alt="source: api/middleware.py" src="https://img.shields.io/badge/source-api%2Fmiddleware.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 15 min" src="https://img.shields.io/badge/read-15%20min-555555">
</p>

[Docs](../README.md) › [Security](../README.md#security) › **Threat model** · page 32 of 57

What SerpFlow is trying to prevent, what it does about each threat, and what it **deliberately does not** defend against.

**Three facts set the shape of this document.** SerpFlow:

- is **multi-tenant** ([row-level security](../database/rls.md))
- holds **other people's upstream API credentials** ([bring your own key](byok.md))
- stores search results that can contain **personal data** ([executor: retention](../architecture/executor.md#retention))

## Assets

| Asset | Why it matters | Where it lives |
| --- | --- | --- |
| Upstream SerpApi and Groq credentials | directly spendable money belonging to a customer | [`upstream_credentials`](../database/schema.md#upstream_credentials), envelope-encrypted ([credentials](credentials.md)) |
| SerpFlow API keys | access to that spend, and to tenant data | [`api_keys`](../database/schema.md#api_keys), HMAC-hashed ([API keys](api-keys.md)) |
| Deployment secrets | the KEK and the pepper unlock the two rows above | process environment only ([secrets](secrets.md)) |
| Cached SERP payloads | may contain personal data (reviewer identities, profiles) | object storage, indexed by [`cache_entries`](../database/schema.md#cache_entries) |
| Run and plan history | reveals what an organization is researching | [`runs`](../database/schema.md#runs), [`plans`](../database/schema.md#plans) |
| Audit log | the record everything else is checked against | [`audit_log`](../database/schema.md#audit_log) |

## Trust boundaries

```
browser / SDK / CLI / agent
        |  API key or bearer token
        v
 [ API layer ]  authn, authz, rate limit, tenant scoping
        |
        v
 [ services ]  planner, cache, executor      <- credentials decrypt here only
        |
        v
 postgres (RLS)   redis   kafka   object storage
        |
        v
 SerpApi, Groq                                <- calls carrying a tenant's key
 Gmail, webhook targets, OTLP collector       <- outbound, deployment-owned
```

- **Inside the service boundary, everything is trusted with everything**
- **The enforced boundaries:** caller to API, tenant to tenant, and service to upstream
- **The MCP server sits inside the boundary.** It runs the services in-process against the database, so it needs the deployment's secrets, not just an API key ([MCP: how it runs](../sdks/mcp.md#how-it-runs))

## Threats and responses

| Threat | Main defence | Implemented in | Section |
| --- | --- | --- | --- |
| Cross-tenant access | app guards + RLS, `404` not `403` | [RLS](../database/rls.md), [ADR 0011](../adr/0011-rls-plus-application-guards.md) | [↓](#cross-tenant-data-access) |
| Database dump | envelope encryption, peppered HMAC; KEK and pepper not in the DB | [credentials](credentials.md#envelope-encryption), [ADR 0005](../adr/0005-envelope-encryption.md), [ADR 0004](../adr/0004-hmac-for-api-keys.md) | [↓](#credential-theft-from-the-database) |
| Exfiltration via the API | credential fields absent from every schema, test-enforced | [credentials](credentials.md#never-in-a-response), [ADR 0006](../adr/0006-no-credential-field-in-schemas.md) | [↓](#credential-exfiltration-through-the-api) |
| Leakage via logs | redaction filter on four routes | [credentials](credentials.md#never-in-a-log), [observability](../operations/observability.md#logging) | [↓](#credential-leakage-through-logs) |
| Spend abuse | four independent limits | [executor](../architecture/executor.md#budget-enforcement), [API keys](api-keys.md#service-principal-sessions) | [↓](#spend-abuse) |
| Wrong data served as live | deterministic guard, freshness, provenance headers | [caching](../architecture/caching.md#the-entity-and-numeral-guard), [ADR 0003](../adr/0003-deterministic-semantic-guard.md), [ADR 0009](../adr/0009-freshness-gates-warmth.md) | [↓](#stale-or-wrong-cached-data-served-as-live) |
| Personal data | separate permission, `pii_risk`, a shorter retention deadline | [executor](../architecture/executor.md#retention) | [↓](#personal-data-in-cached-payloads) |
| Audit tampering | append-only trigger + hash chain | [RLS: the audit log](../database/rls.md#the-audit-log), [ADR 0012](../adr/0012-append-only-audit-log.md) | [↓](#tampering-with-the-audit-log) |
| Mock mistaken for live | absolute mode precedence, loud replay misses | [execution modes](../product/execution-modes.md), [ADR 0010](../adr/0010-test-key-mode-precedence.md) | [↓](#replay-or-mock-data-mistaken-for-live) |
| Session theft | hashed refresh tokens, 15-minute access tokens | [API: authentication](../api/overview.md#authentication) | [↓](#session-theft) |
| Denial of service | body cap, rate limit, bounded planning | [API: rate limiting](../api/overview.md#rate-limiting), [planner](../architecture/planner.md#stage-d-path-find-and-generate-candidates) | [↓](#denial-of-service) |

### Cross-tenant data access

**Scenario:** an authenticated caller for org A requests a run id belonging to org B.

- **Enforced twice** ([ADR 0011](../adr/0011-rls-plus-application-guards.md)):
  - the application compares `org_id` on every resource fetched by id
  - PostgreSQL row-level security on **24 tables** is the backstop for a query that forgets ([covered tables](../database/rls.md#covered-tables))
- **The response is `404`, never `403`:** confirming that an id exists in another organization is itself a leak
- **RLS only binds when the database role lets it.** A superuser or the tables' owner bypasses it, which is the local default; production needs the role change in [deployment guide, step 8](../deployment/deployment-guide.md#8-make-row-level-security-bind)
- **The cache is partitioned by project by default** ([partitioning](../architecture/caching.md#partitioning))
  - a shared organization cache needs the organization's `cache_scope` set to `organization` **and** the project's `shared_cache_enabled`
  - even then, the partition key **never spans organizations**
- More: [row-level security](../database/rls.md)

### Credential theft from the database

**Scenario:** an attacker obtains a database dump.

- **Credentials are AES-256-GCM encrypted** under a per-credential DEK, itself wrapped by a KEK that lives **only in the process environment** ([envelope encryption](credentials.md#envelope-encryption), [ADR 0005](../adr/0005-envelope-encryption.md))
  - the dump holds ciphertext and wrapped DEKs, nothing more
- **API key hashes are HMAC-SHA256 under a server-side pepper**, also not in the database ([API keys: hashing](api-keys.md#hashing-hmac-sha256-not-argon2), [ADR 0004](../adr/0004-hmac-for-api-keys.md))
  - so a guessed key cannot be verified offline either
- **A dump alone is not enough. A dump plus the environment is**, which is why production guidance puts the KEK in a KMS ([secrets: production checklist](secrets.md#production-checklist))
- **A rotated credential's envelope stays at rest after its grace window**, unusable but not erased, until it is deleted ([validation and revocation](credentials.md#validation-and-revocation))

### Credential exfiltration through the API

**Scenario:** someone looks for an endpoint that returns the key they stored.

- **There is no such field.** Not excluded, not redacted: **absent** from every response model in `app/schemas` ([ADR 0006](../adr/0006-no-credential-field-in-schemas.md))
- **A test walks the response models and asserts it**, because this rule is the one most likely to be broken by accident (a future `model_dump()`, or a convenience field on a subclass)
- **Decryption happens in four functions**, each about to make an upstream call with the result: the executor, credential validation, quota reconciliation, and `resolve_llm` for a Groq key ([where it is decrypted](credentials.md#where-it-is-decrypted))

### Credential leakage through logs

**A secret can reach a log four ways:** the message, the args, an `extra=` attribute, or an exception carried on the record.

- **`CredentialRedactionFilter` covers all four** ([never in a log](credentials.md#never-in-a-log))
  - unit tests cover the message, the args and pattern matching; the `extra=` and exception routes are implemented but not yet tested directly
- **Error responses** carry a code, a sentence and a request id. Never a stack trace ([API: errors](../api/overview.md#errors))

### Spend abuse

**Scenario:** a compromised key, or an agent in a loop, burns the organization's SerpApi quota.

**Four independent limits:**

1. **Budgets** at organization, project, API key and session scope; every applicable one must have room, checked before every upstream call ([executor: budget enforcement](../architecture/executor.md#budget-enforcement))
2. **Service principal sessions** have their own `session_cap`, so a machine caller is bounded **as an identity**, not as a share of a human's key ([API keys: service principal sessions](api-keys.md#service-principal-sessions))
   - the cap is enforced only when the MCP client sets `SERPFLOW_MCP_SESSION`, and then before each call; without it every tool call opens a fresh session, the cap is never checked, and an agent in a loop never reaches `SESSION_CAP_EXCEEDED`
   - the key's own budget is then the cumulative limit: a service key created with a `session_cap` gets an `api_key` budget of the same size
3. **Rate limiting** per principal and path, on plan, search and run ([API: rate limiting](../api/overview.md#rate-limiting))
4. **Upstream quota** is SerpApi's own limit; SerpFlow reconciles against it and reports it separately ([credentials: validation and revocation](credentials.md#validation-and-revocation))
   - `BUDGET_EXHAUSTED` and `UPSTREAM_QUOTA_EXHAUSTED` are never conflated: different causes, different fixes ([troubleshooting](../operations/troubleshooting.md#budget_exhausted-against-upstream_quota_exhausted))

- **A `test` key is not a way around the budget:** it spends nothing upstream, but the budget check runs in every mode

### Stale or wrong cached data served as live

**The cache is the product**, so a bad hit is a **correctness** failure, not a performance one.

- **The deterministic entity, numeral and version guard runs independently of the cosine score** ([the entity and numeral guard](../architecture/caching.md#the-entity-and-numeral-guard), [ADR 0003](../adr/0003-deterministic-semantic-guard.md))
  - "Nvidia Q3 2024 revenue" and "Nvidia Q4 2024 revenue" embed close together, and are rejected on exact set equality
- **Freshness bounds are enforced before reuse:** a warm entry that misses the step's freshness requirement does not count as warm ([available is not acceptable](../architecture/marginal-replanning.md#available-is-not-acceptable), [ADR 0009](../adr/0009-freshness-gates-warmth.md))
- **Provenance is never implicit** ([API: provenance headers](../api/overview.md#provenance-headers)):
  - `X-SerpFlow-Mode` and `X-SerpFlow-Catalog-Version` are on **every** response
  - `X-SerpFlow-Cache`, `X-SerpFlow-Age`, `X-SerpFlow-Matched-Query` and `X-SerpFlow-TTL-Source` are on every `POST /v1/search` response, describing the first step
  - per-step provenance for the rest of a chain is on the run itself ([executor: per-step record](../architecture/executor.md#per-step-record))
- **`X-SerpFlow-Mode` is always present**, so a replayed or mocked *run* is never presented as live. A cached payload written by such a run is another matter: see [the residual risk below](#replay-or-mock-data-mistaken-for-live)
- **Operators can report a false hit** from the Run Inspector: the report increments `serpflow_semantic_false_hit_reports_total`, and can invalidate the entry ([worked example](../api/examples.md#report-a-bad-semantic-hit))

### Personal data in cached payloads

**A `google_maps_contributor_reviews` payload is one named person's review history across venues.** That is not anonymous infrastructure data.

- **Raw payload access has its own permission** (`payload:read`), separate from run visibility ([roles](api-keys.md#roles))
- **Steps carry a `pii_risk` level**, from the engine's catalog entry, and runs carry `max_pii_risk` ([volatility and PII](../architecture/catalog.md#volatility-and-pii))
- **High-PII runs get a shorter retention deadline:** `expires_at` 7 days out against 30
  - **the deadline is recorded, not yet enforced:** nothing deletes a run when it passes ([executor: retention](../architecture/executor.md#retention))
- **Payloads are content-addressed in object storage**, not inlined into rows that are read casually ([caching: object storage](../architecture/caching.md#object-storage))

### Tampering with the audit log

**Scenario:** a compromised admin edits history to hide an action.

- **Append-only at the database level** ([ADR 0012](../adr/0012-append-only-audit-log.md)):
  - a trigger refuses `UPDATE` unconditionally
  - it refuses `DELETE` unless the transaction set `app.audit_purge`, which only `AuditService.allow_purge` does, and only the seed's demo reset calls ([RLS: the audit log](../database/rls.md#the-audit-log))
- **Hash chained per organization:** `GET /v1/audit/verify` walks the chain and reports the first break, by sequence number
- **Tampering is therefore both hard and detectable**

### Replay or mock data mistaken for live

**Scenario:** a demo or test run is read as a real result.

- **Mode precedence is absolute:** a `test` API key routes to the deterministic mock regardless of `SERPFLOW_MODE`, and no configuration overrides it ([ADR 0010](../adr/0010-test-key-mode-precedence.md), [execution modes](../product/execution-modes.md#who-chooses-and-precedence))
- **Replay never silently falls back to the network:** a cassette miss raises `REPLAY_CASSETTE_MISS` instead of quietly spending a credit ([troubleshooting](../operations/troubleshooting.md#replay_cassette_miss))
- **Choosing a billable mode per request needs its own permission** (`run:mode_override`); downgrading to `replay` needs none ([execution modes: permission](../product/execution-modes.md#permission))
- **`X-SerpFlow-Mode` on plan and search responses is the resolved mode** of that request; on other routes it is the instance default, or `MOCK` for a test key ([`app/api/middleware.py`](../../backend/app/api/middleware.py))
- **Residual risk: the cache does not separate modes.** Every result is written to the cache with the mode that produced it (`cache_entries.mode`), but neither the exact nor the semantic lookup filters on it, and the partition key is the project (or organization), not the mode ([`app/services/cache/service.py`](../../backend/app/services/cache/service.py))
  - so a mock payload written by a `test` key, or a replayed one, can later be served as an exact or semantic hit to a `live` run in the same partition
  - that run then reports `cache_layer` `exact` or `semantic` and `X-SerpFlow-Mode: LIVE`; nothing on the response says the payload was mock data
  - until lookups filter on mode, keep `test` keys and live traffic in **separate projects**, and do not enable organization-wide cache sharing for a project that test keys use ([organization-level sharing](../architecture/caching.md#organization-level-sharing))

### Session theft

- **Refresh tokens are stored hashed (HMAC under the pepper), with rotation lineage**: each refresh revokes the old session and records `rotated_from` on the new one, and a rotated token presented again is refused ([`rotate_refresh`](../../backend/app/services/auth/service.py))
  - reuse is refused, not treated as theft: it does not revoke the rest of that token's lineage
- **Access tokens live 15 minutes**, refresh tokens 14 days ([secrets: JWT secret](secrets.md#jwt-secret))
- **The SSE endpoint needs an access token as a query parameter**, because `EventSource` cannot set headers ([streaming: authentication](../api/streaming.md#authentication))
  - never an API key (a value starting `sf_` is ignored there), and never a refresh token (the token type is checked)
  - **the parameter is read by the shared `get_principal` dependency**, so every authenticated route accepts `?access_token=`, not only the stream ([`app/api/deps.py`](../../backend/app/api/deps.py))

### Denial of service

- **`MAX_REQUEST_BODY_BYTES`** caps request size (1 MiB by default), checked against `Content-Length`, with `REQUEST_TOO_LARGE` (413)
- **Rate limiting** is per principal and path, not per address: `RATE_LIMIT_PER_MINUTE` (240) in a 60-second window, on `POST /v1/plan`, `/v1/search` and `/v1/run` only ([`rate_limit`](../../backend/app/api/deps.py)). Every other route is unlimited
- **Planning is bounded** by `PLANNER_MAX_CANDIDATES` and `PLANNER_MAX_HOPS`, so a pathological intent cannot make the graph search explode ([candidate plurality](../architecture/planner.md#candidate-plurality-is-a-hard-requirement))
- **Rate limiting fails open if Redis is unavailable.** A deliberate choice ([Redis: degradation](../operations/redis.md#degradation)):
  - a cache outage taking down the API is worse than a brief window without rate limits
  - budgets and session caps are still enforced in PostgreSQL, and the upstream quota by SerpApi

### Exposed surfaces

- **`/metrics` is unauthenticated**, and the bundled nginx proxies it ([`frontend/nginx.conf`](../../frontend/nginx.conf)). Its labels include organization and project ids and per-engine spend, so a public `/metrics` leaks which tenants exist and how much they spend
  - block it at the edge, as [deployment guide, step 9](../deployment/deployment-guide.md#9-put-tls-in-front) does; Prometheus scrapes the backend on the internal network and is unaffected ([observability: metrics](../operations/observability.md#metrics))
- **`/healthz` and `/readyz` are unauthenticated** by design ([observability: health](../operations/observability.md#health))
- **Recorded client addresses can be spoofed.** The API runs uvicorn with `proxy_headers=True` and `forwarded_allow_ips="*"` ([`app/server.py`](../../backend/app/server.py)), so uvicorn replaces the socket peer with the **leftmost**, client-supplied `X-Forwarded-For` entry
  - `client_ip()` reads the right-hand entry when `TRUSTED_PROXY_HOPS` proxies appended to the header, which holds behind the bundled nginx (`TRUSTED_PROXY_HOPS=1`)
  - with `TRUSTED_PROXY_HOPS=0`, or a header shorter than the configured hops, it falls back to that already-replaced peer, so the caller chooses the address. The comments in `.env.example` and `config.py` say the opposite
  - what it affects: the `ip` on audit entries, `api_keys.last_used_ip`, `users.last_login_ip` and session records. Rate limiting is keyed by principal, so it is not affected
  - until that changes, keep a proxy that sets `X-Forwarded-For` in front of the API, and treat recorded addresses as hints, not evidence

## Out of scope

Stated plainly, because an unstated boundary reads as an oversight:

- **A compromised host.** With the process environment, an attacker has the KEK and the pepper ([secrets](secrets.md#inventory)). Nothing in the application defends against that; KMS and host hardening do ([production](../deployment/production.md#before-anything-else))
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

- [Bring your own key](byok.md): whose keys SerpFlow holds, and where they come from
- [Upstream credentials](credentials.md): envelope encryption, decryption sites, revocation
- [API keys](api-keys.md): key format, roles and service sessions
- [Secrets](secrets.md): the deployment secrets a compromised host would expose
- [Row-level security](../database/rls.md): the database half of tenant isolation
- [ADR 0011](../adr/0011-rls-plus-application-guards.md) and [ADR 0012](../adr/0012-append-only-audit-log.md): isolation enforced twice, and an audit log that refuses edits
- [Production](../deployment/production.md#before-anything-else): the hardening this model assumes
- [SECURITY.md](../../SECURITY.md#reporting-a-vulnerability): how to report what this page missed

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Row-level security](../database/rls.md) | [Docs index](../README.md) | [Bring your own key](../security/byok.md) |
