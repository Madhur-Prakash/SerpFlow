# API keys

A SerpFlow API key authenticates a caller to SerpFlow. It is a different thing
from the [upstream SerpApi credential](credentials.md), which authenticates
SerpFlow to SerpApi, and the two are never conflated anywhere in the codebase.

Implementation: [`app/core/security.py`](../../backend/app/core/security.py),
[`app/services/auth/service.py`](../../backend/app/services/auth/service.py).

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

The environment segment matters more than it looks: a `test` key routes to the
deterministic mock **regardless** of `SERPFLOW_MODE`, and
`parse_api_key(...).is_test` is readable before a database round trip. The
precedence is absolute and is not overridable by configuration.

The project prefix is stored in plaintext and uniquely indexed, which is what
turns authentication into an index lookup rather than a scan that HMACs every
key in the system to find a match.

## Hashing: HMAC-SHA256, not Argon2

```python
def hash_api_key(plaintext: str) -> str:
    return hmac.new(
        settings.api_key_pepper.encode("utf-8"),
        plaintext.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
```

This is deliberate, and the opposite of the rule for passwords.

Password hashing is slow on purpose because passwords are low entropy and
guessable; the cost is paid once per login. An API key has 190+ bits of
entropy from a CSPRNG. There is no dictionary, no reuse across sites, and no
feasible brute force to stretch against. Argon2 would add 50-100 ms to **every
authenticated request** and buy nothing.

The pepper is server-side, in `API_KEY_PEPPER`, never in the database.
A database dump alone does not let an attacker verify a guessed key.

Comparison is always `hmac.compare_digest`.

## What is stored

```
project_prefix          plaintext, uniquely indexed
key_hash                HMAC-SHA256 hex
display                 sf_live_pm8kd3_••••
environment, role, is_service_principal, session_cap
last_used_at, last_used_ip, use_count
expires_at, revoked_at, rotation_grace_until
```

The plaintext is returned exactly once, from the creation response, and never
again. There is no endpoint that can reveal it, because nothing anywhere holds
it.

The display form uses a bullet, not asterisks, and never shows any part of the
secret — not the last four characters either. A prefix plus four real
characters narrows a search; a prefix alone does not.

## Resolution

```
parse            structural, rejects anything not matching the pattern
redis            principal cache, 60 s TTL (REDIS_PRINCIPAL_CACHE_TTL)
postgres         indexed on (project_prefix, environment, key_hash)
verify           hmac.compare_digest against the stored hash
checks           revoked (unless in rotation grace), expired
record           last_used_at, last_used_ip, use_count
```

The Redis principal cache exists because the resolved principal — org, project,
role, permission set, session cap — is read on every single request and changes
rarely. 60 seconds is short enough that a revocation propagates quickly on its
own, and revocation does not wait for it anyway: `rotate` and `revoke` call
`invalidate_principal(key_hash)` directly.

If Redis is down, resolution falls through to PostgreSQL. Authentication does
not depend on the cache being up.

## Rotation

```http
POST /v1/keys/{id}/rotate
```

Mints a replacement with the same role and project, marks the old key revoked,
and sets `rotation_grace_until` (60 minutes by default). Both keys authenticate
during the window, so a deploy can roll without a flag day. The old key's
principal entry is invalidated immediately so the grace window is enforced from
the database rather than from a stale cache.

```http
DELETE /v1/keys/{id}
```

Revokes with no grace window.

## Roles

Five roles, cumulative except for `service`:

| Role | Can |
| --- | --- |
| `owner` | everything, including rotating credentials and deleting the org |
| `admin` | manage projects, members, keys, budgets, policies |
| `developer` | execute searches, read runs and payloads |
| `analyst` | plan, read runs and analytics — **cannot execute** |
| `service` | a narrow machine scope: plan, execute, read runs, payloads, catalog, budget and cache |

`analyst` is a real distinction rather than a cosmetic one. `POST /v1/plan`
calls a language model and spends zero SerpApi credits; `POST /v1/search`
spends real money. Separating them means an analyst can explore routing
behaviour all day without touching the budget.

`service` is not a point on the human ladder. `analyst` through `owner` are
cumulative and are asserted to be so by a test; `service` is defined
independently, so a machine principal cannot accidentally inherit a permission
that gets added to `developer` later.

Checks are centralised:

```python
@router.post("/search", dependencies=[Depends(require(Permission.RUN_EXECUTE))])
```

No business-logic module runs its own authorization check, and `can()` denies
by default: an unmapped role has no permissions rather than all of them.

## Service principal sessions

A machine caller — an MCP agent, a scheduled job — opens a
`service_sessions` row carrying its own `session_cap` and `credits_used`. That
means an agent is budgeted as an identity in its own right, not as a human with
a shared key, and a runaway loop hits `SESSION_CAP_EXCEEDED` instead of the
organization's monthly budget.

## Test keys

```bash
make seed    # prints a usable sf_test_... key
```

A `test` key needs no upstream credential, spends no SerpApi credits, and
returns deterministic mock data with `X-SerpFlow-Mode: MOCK`. Every example in
[the API docs](../api/examples.md) uses one.

## Related

- [Upstream credentials](credentials.md)
- [Secrets](secrets.md)
- [Threat model](threat-model.md)
