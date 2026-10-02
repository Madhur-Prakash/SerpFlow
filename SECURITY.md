# Security policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue.
Use GitHub's private vulnerability reporting on this repository, or email the
maintainers listed in `pyproject.toml`.

Include what you did, what happened, and what you expected. A proof of concept
helps. We will acknowledge within a few days and keep you updated while we
work on a fix.

Please do not run automated scanners against a deployment you do not own.

## What SerpFlow holds

SerpFlow is a control plane for a paid upstream API, so it holds three classes
of sensitive material:

| Material | Where it lives | Protection |
| --- | --- | --- |
| Upstream SerpApi credentials | `upstream_credentials` | Envelope encryption: a random per-credential AES-256-GCM data key, itself wrapped by a key-encryption key. Only the ciphertext and the wrapped key are stored. |
| SerpFlow API keys | `api_keys` | HMAC-SHA256 under a server-side pepper. The plaintext is shown once at creation and never again. |
| User passwords | `users` | Argon2id, `time_cost=3`, `memory_cost=64MiB`, `parallelism=4`. |
| Cached SERP payloads | object storage | Content-addressed, referenced by `payload_ref`. Retention is shorter for high-PII-risk engines. |

### Why API keys are not Argon2 hashed

This is a deliberate decision, not an oversight. A SerpFlow API key carries
more than 190 bits of entropy, so there is no brute-force surface for a slow
hash to protect. Argon2 would add 50 to 100 milliseconds to every single
authenticated request for no security gain. Keys use HMAC-SHA256 under a
server-side pepper with `hmac.compare_digest`, which is constant time and
sub-millisecond. Passwords, which are low entropy and human chosen, use
Argon2id.

See [`docs/security/api-keys.md`](docs/security/api-keys.md).

### The credential boundary

The upstream SerpApi credential is decrypted in exactly one place: the executor
service, immediately before issuing an upstream call. It is never decrypted in
an API handler, never attached to a model, never written to a log, and does not
appear as a field in any Pydantic response schema anywhere in the codebase.

That last point is enforced by a test that walks every model in `app/schemas`
and fails if a field named `api_key`, `secret`, `ciphertext` or `encrypted_dek`
appears on a response model. The field is **absent**, not excluded, because
excluded fields leak through serialisation bugs.

See [`docs/security/credentials.md`](docs/security/credentials.md).

### Log redaction

Structured logging runs every record through a redaction filter that scrubs the
message, the formatted arguments, the record attributes and the exception path.
It recognises SerpFlow key format, SerpApi key format, Groq and OpenAI token
formats, JWTs, and `key=value` pairs whose key looks sensitive.

The exception path is covered explicitly because that is where credentials
actually leak in practice: a handler catches an upstream error whose message
echoes the request URL, and the URL contains the key.
`tests/unit/test_security.py` asserts this.

## Tenant isolation

Every tenant-scoped table carries `org_id` with an index. Isolation is enforced
twice:

1. **Application guards.** `app/api/deps.py` resolves the principal, scopes the
   transaction, and asserts that any resource fetched by id belongs to the
   caller's organization. Cross-tenant access returns `404`, not `403`, because
   confirming that an id exists in another organization is itself a leak.
2. **PostgreSQL row-level security.** Every scoped table has a policy keyed on
   `app.current_org`, set per transaction with `SET LOCAL`. An unset value
   matches nothing, so a query issued without the tenant guard returns no rows
   rather than every row.

See [`docs/database/rls.md`](docs/database/rls.md).

## Audit log

The audit log is append-only at the database level: a trigger refuses `UPDATE`
unconditionally and refuses `DELETE` unless the transaction has explicitly set
`app.audit_purge`, which only organization deletion does. Each entry stores the
hash of the previous entry for its organization, so any insertion, edit or
removal shows up as a chain break at a known sequence number.
`GET /v1/audit/verify` walks the chain and reports the first break.

## Retention

Cached SERPs are not anonymous infrastructure data. A
`google_maps_contributor_reviews` payload is one named person's complete review
history across venues. Engines declare a `pii_risk` level, runs inherit the
highest level any of their steps carries, and retention follows:

```
standard pii_risk    30 days
pii_risk: high        7 days
```

Both are configurable per project.

## Supported versions

SerpFlow is pre-1.0. Security fixes land on `main`; there are no maintained
release branches yet.

## Hardening a deployment

The defaults in `.env.example` are development defaults and several are marked
`CHANGE ME`. Before deploying:

- Replace `JWT_SECRET`, `API_KEY_PEPPER` and `CREDENTIAL_KEK`.
- Move the credential KEK to a managed KMS, or to `age` for self-hosting. The
  `kek_id` column exists so you can rotate without re-encrypting everything at
  once.
- Set `ENVIRONMENT=production` and `DEBUG=false`.
- Terminate TLS in front of the API, and restrict `CORS_ORIGINS` to the
  frontend origin.
- Put the API behind a reverse proxy that enforces request size limits as well;
  the application limit is a second line, not the only one.

See [`docs/deployment/production.md`](docs/deployment/production.md) and
[`docs/security/secrets.md`](docs/security/secrets.md).
