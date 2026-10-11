# API keys

<p>
  <a href="../README.md#security"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="roles: 5 built-in + custom" src="https://img.shields.io/badge/roles-5%20built--in%20%2B%20custom-6E40C9">
  <img alt="HMAC: SHA-256" src="https://img.shields.io/badge/HMAC-SHA--256-6E40C9">
  <img alt="Argon2id: passwords" src="https://img.shields.io/badge/Argon2id-passwords-6E40C9">
  <a href="../../backend/app/core/security.py"><img alt="source: core/security.py" src="https://img.shields.io/badge/source-core%2Fsecurity.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 11 min" src="https://img.shields.io/badge/read-11%20min-555555">
</p>

[Docs](../README.md) › [Security](../README.md#security) › **API keys** · page 35 of 57

**A SerpFlow API key authenticates a caller to SerpFlow.**

- It is a different thing from the [upstream SerpApi credential](credentials.md), which authenticates SerpFlow to SerpApi
- The two are **never conflated** anywhere in the codebase
- How a request presents one (`X-API-Key`, or `Authorization: Bearer sf_...`): [API: authentication](../api/overview.md#authentication)

Implementation: [`app/core/security.py`](../../backend/app/core/security.py) · [`app/services/auth/service.py`](../../backend/app/services/auth/service.py) · [`app/core/permissions.py`](../../backend/app/core/permissions.py) · table: [`api_keys`](../database/schema.md#api_keys)

## Format

```
sf_<env>_<project_prefix>_<secret>
sf_live_pm8kd3_v1a7Qx9mNc2PfLz4Rt6WbYs8KdJh3Gn5
```

| Part | Width | Purpose |
| --- | --- | --- |
| `sf_` | 3 | identifies the key as SerpFlow's, in a log or a leaked file |
| `env` | `live` or `test` | mode precedence, decided before any lookup |
| `project_prefix` | 6 lowercase alphanumerics | the project's `key_prefix`: plaintext, indexed |
| `secret` | 32 alphanumerics | the actual secret, from a 62-character alphabet: about 190 bits |

- **Anything not matching `^sf_(live|test)_[a-z0-9]{6}_[A-Za-z0-9]{32}$` is rejected** by `parse_api_key` before any lookup, as `INVALID_API_KEY` ([API: key format](../api/overview.md#key-format))
- **The environment segment matters more than it looks**
  - a `test` key routes to the deterministic mock **regardless** of `SERPFLOW_MODE` ([execution modes](../product/execution-modes.md#who-chooses-and-precedence))
  - `parse_api_key(...).is_test` is readable **before** a database round trip
  - the precedence is absolute, and no configuration overrides it ([ADR 0010](../adr/0010-test-key-mode-precedence.md))
- **The project prefix is plaintext**, and unique per project (`projects.key_prefix`)
  - lookup filters on `project_prefix`, `environment` and `key_hash`, all indexed, so authentication is an **index lookup**, not a scan that HMACs every key in the system to find a match

## Hashing: HMAC-SHA256, not Argon2

```python
def hash_api_key(plaintext: str) -> str:
    return hmac.new(
        settings.api_key_pepper.encode("utf-8"),
        plaintext.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
```

**Deliberate, and the opposite of the rule for passwords:**

| | Passwords | API keys |
| --- | --- | --- |
| Entropy | low, human-chosen, guessable | 190+ bits from a CSPRNG |
| Reuse across sites | common | none |
| Brute force | feasible: stretch it | not feasible |
| Cost of a slow hash | paid once per login | would be paid on **every request** |
| So | **Argon2id** | **HMAC-SHA256** |

- **Argon2 would add 50-100 ms to every authenticated request** and buy nothing
- **The pepper is server-side**, in [`API_KEY_PEPPER`](secrets.md#pepper), never in the database: a dump alone does not let an attacker verify a guessed key
- **The same pepper hashes other short-lived handles** through `hash_opaque_token`: refresh sessions, email-verification and password-reset tokens, and webhook channel secrets. Changing it breaks every key, session and pending link at once ([secrets: pepper](secrets.md#pepper))
- **The MCP server hashes keys in-process**, so it needs the API's exact `API_KEY_PEPPER` ([MCP: configuration](../sdks/mcp.md#configuration))
- **Comparison is always `hmac.compare_digest`**
- More: [ADR 0004](../adr/0004-hmac-for-api-keys.md#api-keys-hmac-sha256-under-a-server-side-pepper)

## What is stored

```
project_prefix          plaintext, indexed with environment
key_hash                HMAC-SHA256 hex, uniquely indexed
display                 sf_live_pm8kd3_••••
environment, role, is_service_principal, session_cap
last_used_at, last_used_ip, use_count
expires_at, revoked_at, revoked_reason
rotated_from_id, rotation_grace_until
```

- **The plaintext is returned exactly once**, in the creation response, and never again
  - no endpoint can reveal it, because nothing anywhere holds it
- **The display form never shows any part of the secret**, not even the last four characters
  - a prefix plus four real characters narrows a search; a prefix alone does not

## Resolution

```
parse            structural, rejects anything not matching the pattern
hash             HMAC-SHA256 of the presented key, under the pepper
redis            principal cache, keyed by that hash, 60 s TTL (REDIS_PRINCIPAL_CACHE_TTL)
postgres         on a cache miss: WHERE project_prefix, environment, key_hash
                 (ix_api_keys_prefix_env, ix_api_keys_hash UNIQUE)
verify           hmac.compare_digest against the stored hash
checks           revoked (unless still inside rotation_grace_until), expired
record           last_used_at, last_used_ip, use_count
```

- **Why the Redis principal cache:** the resolved principal (org, project, role, session cap) is read on **every** request and changes rarely ([Redis: what lives in it](../operations/redis.md#what-lives-in-it))
- **Permissions are re-derived from the role on every request**, cache hit or not, so a change to a [custom role](#custom-roles) applies at once
- **A cache hit skips the database row**, and with it the revocation and expiry checks and the `last_used_*` update. Two consequences:
  - an expiry that falls inside the 60-second window takes effect when the entry lapses
  - revocation does not wait for it: `DELETE /v1/keys/{id}` calls `invalidate_principal(key_hash)` directly
- **If Redis is down**, resolution falls through to PostgreSQL. Authentication never depends on the cache

## Rotation

```http
POST /v1/keys/{id}/rotate        {"grace_minutes": 60}
```

- **Mints a replacement** with the same project, environment, role, service-principal flag and session cap, named `<name> (rotated)`, with `rotated_from_id` pointing back
- **Sets the old key's `rotation_grace_until`** (`grace_minutes`, 60 by default, at most 10,080): both keys authenticate during the window, so a deploy can roll without a flag day
- **It does not revoke the old key, and does not touch the principal cache.** Resolution refuses only a key that is revoked **and** past its grace window, so an old key that is never revoked keeps authenticating after the window closes. Finish a rotation with `DELETE` on the old key ([`resolve_api_key`](../../backend/app/services/auth/service.py))

```http
DELETE /v1/keys/{id}
```

- **Sets `revoked_at` and invalidates the principal cache entry immediately**
- **On a key that was never rotated, it stops working at once.** On a rotated key whose `rotation_grace_until` is still ahead, it keeps working until the window closes
- Both operations need `key:write` and are audited (`api_key.rotated`, `api_key.revoked`)
- Symptoms and fixes: [troubleshooting: a revoked key still works](../operations/troubleshooting.md#a-revoked-key-still-works)

## Roles

**Five built-in roles**, cumulative except for `service` ([`app/core/permissions.py`](../../backend/app/core/permissions.py)):

| Role | Can |
| --- | --- |
| `owner` | everything: adds rotating and revoking credentials (`credential:rotate`) and defining custom roles (`role:write`) |
| `admin` | manage members, projects (engine policy and cache settings included), any API key, budgets, alerts; attach credentials; read and export the audit log; read roles |
| `developer` | execute searches, replay runs, choose a billable mode per request, read payloads, invalidate cache entries, create API keys (`key:project_write`), run the benchmark |
| `analyst` | plan, read runs, budgets, cache, analytics, benchmark results, catalog, alerts and key listings: **cannot execute** |
| `service` | a narrow machine scope: plan, execute, read runs, payloads, catalog, budget and cache |

- **Some permissions are granted but not yet checked by any route** ([`app/api/v1`](../../backend/app/api/v1)):
  - `org:billing` and `org:delete` (owner): there is no billing or organization-deletion endpoint
  - `policy:write` (admin): engine allow and deny lists, the semantic threshold and TTL overrides are set through `PATCH /v1/projects/{id}`, which checks `project:write`
- **`key:project_write` is broader than its description.** It is meant as "create keys within their own project", but `POST /v1/projects/{id}/keys` checks only that the project belongs to the caller's organization, so a `developer` can mint a key for any project in it, at a role no higher than their own ([`create_key`](../../backend/app/api/v1/organizations.py))

- **`analyst` is a real distinction, not a cosmetic one**
  - `POST /v1/plan` calls a language model and spends zero SerpApi credits; `POST /v1/search` spends real money
  - so an analyst can explore routing behaviour all day without touching the budget
- **`service` is not a point on the human ladder**
  - `analyst` through `owner` are cumulative, and a test asserts it ([`tests/unit/test_security.py`](../../backend/tests/unit/test_security.py))
  - `service` is defined independently, so a machine principal cannot accidentally inherit a permission later added to `developer`
- **A key may never carry a role above its creator's**, compared through `ROLE_ORDER` (`service` < `analyst` < `developer` < `admin` < `owner`)

### Custom roles

- **An owner can define a role** with any permission set, for shapes the built-ins do not cover (migration [`0003_custom_roles`](../database/migrations.md#0003_custom_roles), table [`custom_roles`](../database/schema.md#custom_roles))
- **API:** `GET/POST /v1/roles`, `PATCH/DELETE /v1/roles/{id}`, and `GET /v1/roles/permissions` for every permission a role can hold ([API: identity and access](../api/overview.md#identity-and-access)). Writing needs `role:write` (owner only); reading needs `role:read` (admin and owner)
- **A membership's or API key's `role`** holds either a built-in role name or a custom role's slug, unique per organization
- **The rules** ([`app/services/roles/service.py`](../../backend/app/services/roles/service.py)):
  - the slug is 3 to 40 lowercase letters, digits and hyphens, and may not be a built-in role's name
  - a role needs at least one permission; an unknown permission is rejected on write, and **dropped, not granted**, on read
  - renaming a role keeps its slug, so nobody who holds it loses it
  - deleting a role that a member or key still holds is refused with `CONFLICT`
  - a role name that resolves to nothing grants nothing
- **Tenant-isolated:** a role defined in one organization is invisible to another ([row-level security](../database/rls.md#covered-tables))
- **Assigning one works for memberships** (`PATCH /v1/members/{id}` checks the slug against the organization). **Key creation does not support custom roles yet:** `POST /v1/projects/{id}/keys` compares roles through `ROLE_ORDER`, which knows only built-in names, so a custom slug in `role`, or a creator whose own role is custom, fails the request with `INTERNAL_ERROR` ([`create_key`](../../backend/app/api/v1/organizations.py))

### Checks are centralised

```python
principal: Annotated[Principal, Depends(require(Permission.EXECUTE))]   # POST /v1/search
```

- **No business-logic module runs its own authorization check**
- **`require()` denies by default:** a role that resolves to no permissions can do nothing, not everything
- A refusal is `PERMISSION_DENIED` (403), naming the role and the permission it lacked ([API: errors](../api/overview.md#errors))

## Service principal sessions

- **A machine caller** (an MCP agent) runs under a `service_sessions` row with its own `session_cap` and `credits_used` ([`service_sessions`](../database/schema.md#service_sessions))
  - the MCP server opens one when its key is a service principal (`is_service_principal`) or carries a `session_cap` ([`app/mcp/server.py`](../../backend/app/mcp/server.py))
  - each executed run adds its credits to `credits_used`
- So an agent is **budgeted as an identity in its own right**, not as a human with a shared key
- **`SERPFLOW_MCP_SESSION` decides whether the cap is enforced at all** ([`open_service_session`](../../backend/app/services/auth/service.py)):
  - **set**, it names the session: a call with the same name resumes the open session, across restarts too, and is refused with `SESSION_CAP_EXCEEDED` once `credits_used` has reached `session_cap`
  - the check runs when a call resumes the session, before it executes, and the run's credits are added afterwards ([`app/services/runs.py`](../../backend/app/services/runs.py)), so the call that crosses the cap completes and the next one is refused
  - because the check runs on resume, a session at its cap refuses `plan()` too, although planning spends nothing
  - **unset**, every MCP tool call opens a **new** session (`svcs_...`) with `credits_used = 0`, and the cap is never checked: budgets are the only limit
  - a runaway loop therefore hits `SESSION_CAP_EXCEEDED` only when `SERPFLOW_MCP_SESSION` is set. See [MCP: sessions and budgets](../sdks/mcp.md#sessions-and-budgets) and [connect a client](../sdks/mcp.md#connect-a-client)
- **The cumulative backstop without it is the key's budget**, checked before every upstream call ([executor: budget enforcement](../architecture/executor.md#budget-enforcement)):
  - a service-principal key created through the API with a `session_cap` also gets an `api_key`-scope monthly budget of the same size; the seeded MCP key has `session_cap = 20` and a 20-credit monthly key budget ("MCP service principal cap")
  - so without `SERPFLOW_MCP_SESSION` a looping agent on the seeded key stops at `BUDGET_EXHAUSTED`, not `SESSION_CAP_EXCEEDED`
  - nothing creates a `session`-scope budget row automatically, and the `service` role lacks `budget:write`, so an agent cannot raise its own limits

## Test keys

```bash
make seed    # prints a usable sf_test_... key
```

- **Needs no upstream credential**
- **Spends no SerpApi credits**
- **Returns deterministic mock data**, with `X-SerpFlow-Mode: MOCK` ([provenance headers](../api/overview.md#provenance-headers))
- **Budgets are still checked**, so a test key against an exhausted budget is refused like any other ([executor: budget enforcement](../architecture/executor.md#budget-enforcement))
- Every example in [the API docs](../api/examples.md) uses one, and so should the [SDKs and the CLI](../sdks/overview.md#test-keys) while you integrate
- Why no configuration can override it: [ADR 0010](../adr/0010-test-key-mode-precedence.md), [execution modes](../product/execution-modes.md)

## Related

- [Upstream credentials](credentials.md): the other half of the credential story, the key SerpFlow spends on your behalf
- [Secrets](secrets.md#pepper): the pepper every key hash depends on, and what rotating it costs
- [Threat model](threat-model.md#spend-abuse): where keys, roles and session caps sit among the spend limits
- [ADR 0004](../adr/0004-hmac-for-api-keys.md): why HMAC-SHA256 and not Argon2
- [ADR 0010](../adr/0010-test-key-mode-precedence.md): why a `test` key always means mock
- [MCP server](../sdks/mcp.md#sessions-and-budgets): the main user of service sessions and `SERPFLOW_MCP_SESSION`
- [API overview: identity and access](../api/overview.md#identity-and-access): the key, member and role endpoints
- [Troubleshooting: `INVALID_API_KEY` on a key that looks right](../operations/troubleshooting.md#invalid_api_key-on-a-key-that-looks-right): environment segment, rotation, pepper
- [Bring your own key](byok.md): the upstream keys, as opposed to SerpFlow's own

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Upstream credentials](../security/credentials.md) | [Docs index](../README.md) | [Secrets](../security/secrets.md) |
