# API keys

<p>
  <a href="../README.md#security"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="roles: 5 built-in + custom" src="https://img.shields.io/badge/roles-5%20built--in%20%2B%20custom-6E40C9">
  <img alt="HMAC: SHA-256" src="https://img.shields.io/badge/HMAC-SHA--256-6E40C9">
  <img alt="Argon2id: passwords" src="https://img.shields.io/badge/Argon2id-passwords-6E40C9">
  <a href="../../backend/app/core/security.py"><img alt="source: core/security.py" src="https://img.shields.io/badge/source-core%2Fsecurity.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Security](../README.md#security) › **API keys** · page 28 of 50

**A SerpFlow API key authenticates a caller to SerpFlow.**

- It is a different thing from the [upstream SerpApi credential](credentials.md), which authenticates SerpFlow to SerpApi
- The two are **never conflated** anywhere in the codebase

Implementation: [`app/core/security.py`](../../backend/app/core/security.py) · [`app/services/auth/service.py`](../../backend/app/services/auth/service.py)

## Format

```
sf_<env>_<project_prefix>_<secret>
sf_live_pm8kd3_v1a7Qx9mNc2PfLz4Rt6WbYs8KdJh3Gn5
```

| Part | Width | Purpose |
| --- | --- | --- |
| `sf_` | 3 | identifies the key as SerpFlow's, in a log or a leaked file |
| `env` | `live` or `test` | mode precedence, decided before any lookup |
| `project_prefix` | 6 lowercase alphanumerics | indexed, plaintext, O(1) lookup |
| `secret` | 32 alphanumerics | the actual secret, about 190 bits |

- **The environment segment matters more than it looks**
  - a `test` key routes to the deterministic mock **regardless** of `SERPFLOW_MODE`
  - `parse_api_key(...).is_test` is readable **before** a database round trip
  - the precedence is absolute, and no configuration overrides it
- **The project prefix is plaintext and uniquely indexed**
  - that turns authentication into an **index lookup**, not a scan that HMACs every key in the system to find a match

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
- **The pepper is server-side**, in `API_KEY_PEPPER`, never in the database: a dump alone does not let an attacker verify a guessed key
- **Comparison is always `hmac.compare_digest`**
- More: [ADR 0004](../adr/0004-hmac-for-api-keys.md)

## What is stored

```
project_prefix          plaintext, uniquely indexed
key_hash                HMAC-SHA256 hex
display                 sf_live_pm8kd3_••••
environment, role, is_service_principal, session_cap
last_used_at, last_used_ip, use_count
expires_at, revoked_at, rotation_grace_until
```

- **The plaintext is returned exactly once**, in the creation response, and never again
  - no endpoint can reveal it, because nothing anywhere holds it
- **The display form never shows any part of the secret**, not even the last four characters
  - a prefix plus four real characters narrows a search; a prefix alone does not

## Resolution

```
parse            structural, rejects anything not matching the pattern
redis            principal cache, 60 s TTL (REDIS_PRINCIPAL_CACHE_TTL)
postgres         indexed on (project_prefix, environment, key_hash)
verify           hmac.compare_digest against the stored hash
checks           revoked (unless in rotation grace), expired
record           last_used_at, last_used_ip, use_count
```

- **Why the Redis principal cache:** the resolved principal (org, project, role, permission set, session cap) is read on **every** request and changes rarely
- **60 seconds** is short enough that a revocation propagates on its own
  - and revocation does not wait for it: `rotate` and `revoke` call `invalidate_principal(key_hash)` directly
- **If Redis is down**, resolution falls through to PostgreSQL. Authentication never depends on the cache

## Rotation

```http
POST /v1/keys/{id}/rotate
```

- Mints a replacement with the **same role and project**, marks the old key revoked
- Sets **`rotation_grace_until`** (60 minutes by default): both keys authenticate during the window, so a deploy can roll without a flag day
- The old key's principal entry is invalidated **immediately**, so the grace window is enforced from the database, not from a stale cache

```http
DELETE /v1/keys/{id}
```

- **Revokes with no grace window**

## Roles

**Five built-in roles**, cumulative except for `service`:

| Role | Can |
| --- | --- |
| `owner` | everything, including rotating credentials and deleting the org |
| `admin` | manage projects, members, keys, budgets, policies |
| `developer` | execute searches, read runs and payloads |
| `analyst` | plan, read runs and analytics: **cannot execute** |
| `service` | a narrow machine scope: plan, execute, read runs, payloads, catalog, budget and cache |

- **`analyst` is a real distinction, not a cosmetic one**
  - `POST /v1/plan` calls a language model and spends zero SerpApi credits; `POST /v1/search` spends real money
  - so an analyst can explore routing behaviour all day without touching the budget
- **`service` is not a point on the human ladder**
  - `analyst` through `owner` are cumulative, and a test asserts it
  - `service` is defined independently, so a machine principal cannot accidentally inherit a permission later added to `developer`

### Custom roles

- **An owner can define a role** with any permission set, for shapes the built-ins do not cover (migration `0003_custom_roles`)
- **API:** `GET/POST /v1/roles`, `PATCH/DELETE /v1/roles/{id}`, and `GET /v1/roles/permissions` for every permission a role can hold
- **A membership's or API key's `role`** holds either a built-in role name or a custom role's slug, unique per organization
- **Tenant-isolated:** a role defined in one organization is invisible to another (row-level security)

### Checks are centralised

```python
@router.post("/search", dependencies=[Depends(require(Permission.RUN_EXECUTE))])
```

- **No business-logic module runs its own authorization check**
- **`can()` denies by default:** an unmapped role has no permissions, not all of them

## Service principal sessions

- **A machine caller** (an MCP agent, a scheduled job) opens a `service_sessions` row with its own `session_cap` and `credits_used`
- So an agent is **budgeted as an identity in its own right**, not as a human with a shared key
- **A runaway loop hits `SESSION_CAP_EXCEEDED`**, not the organization's monthly budget

## Test keys

```bash
make seed    # prints a usable sf_test_... key
```

- **Needs no upstream credential**
- **Spends no SerpApi credits**
- **Returns deterministic mock data**, with `X-SerpFlow-Mode: MOCK`
- Every example in [the API docs](../api/examples.md) uses one

## Related

- [Upstream credentials](credentials.md)
- [Secrets](secrets.md)
- [Execution modes](../product/execution-modes.md)
- [Threat model](threat-model.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Upstream credentials](../security/credentials.md) | [Docs index](../README.md) | [Secrets](../security/secrets.md) |
