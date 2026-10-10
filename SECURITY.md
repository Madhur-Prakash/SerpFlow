# Security policy

<p>
  <a href="#reporting-a-vulnerability"><img alt="reporting: private" src="https://img.shields.io/badge/reporting-private-2F6BFF?logo=github&logoColor=white"></a>
  <a href="#maintenance-and-support"><img alt="maintained by: one person" src="https://img.shields.io/badge/maintained%20by-one%20person-555555"></a>
  <a href="#supported-versions"><img alt="supported: main" src="https://img.shields.io/badge/supported-main-3fcf8e"></a>
  <img alt="passwords: Argon2id" src="https://img.shields.io/badge/passwords-Argon2id-6E40C9">
  <img alt="API keys: HMAC-SHA256" src="https://img.shields.io/badge/API%20keys-HMAC--SHA256-6E40C9">
  <img alt="credentials: AES-256-GCM" src="https://img.shields.io/badge/credentials-AES--256--GCM-6E40C9">
  <a href="LICENSE"><img alt="licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-D22128"></a>
</p>

[README](README.md) › **Security policy** · [Docs index](docs/README.md) · [Threat model](docs/security/threat-model.md) · [Contributing](CONTRIBUTING.md)

---

## Maintenance and support

- **SerpFlow is built and maintained by one person, in their own time.** There is no company, security team or on-call rotation behind it
- **It began as a hackathon entry**, and grew from there into a full-scale project
- **Production-ready development is part of that scope**, not an afterthought:
  - versioned Alembic migrations and a self-bootstrapping container
  - multi-tenant isolation, enforced twice (application guards and PostgreSQL RLS)
  - envelope-encrypted credentials, HMAC API keys, Argon2id passwords
  - a hash-chained, append-only audit log
  - traces, metrics, structured logs and alerting rules
  - a documented production deployment
- **What that means for reports:**
  - response is best-effort, usually within a few days, slower around holidays and busy weeks
  - fixes land on `main` as soon as they are ready; there is no fixed patch schedule
  - a clear report with a proof of concept is the fastest path to a fix
- Thank you for reporting responsibly. It matters more on a project with one maintainer, not less

## Reporting a vulnerability

- **Report privately.** Do not open a public issue
- Use **GitHub's private vulnerability reporting** on this repository
- Include:
  - what you did
  - what happened
  - what you expected
  - a proof of concept, if you have one
- You will get an acknowledgement, then updates while a fix is worked on
- **Do not run automated scanners** against a deployment you do not own

## Supported versions

| Version | Supported |
| --- | --- |
| `main` | Yes: security fixes land here |
| Anything else | No: SerpFlow is pre-1.0 and has no maintained release branches yet |

## What SerpFlow holds

SerpFlow is a control plane for a paid upstream API, so it holds sensitive material of four kinds:

| Material | Where it lives | Protection |
| --- | --- | --- |
| Upstream SerpApi credentials | `upstream_credentials` | Envelope encryption: a random per-credential AES-256-GCM data key, wrapped by a key-encryption key. Only the ciphertext and the wrapped key are stored |
| SerpFlow API keys | `api_keys` | HMAC-SHA256 under a server-side pepper. The plaintext is shown once, at creation, and never again |
| User passwords | `users` | Argon2id, `time_cost=3`, `memory_cost=64MiB`, `parallelism=4` |
| Cached SERP payloads | object storage | Content-addressed, referenced by `payload_ref`. Shorter retention for high-PII-risk engines |

### Why API keys are not Argon2-hashed

- **A deliberate decision, not an oversight**
- A SerpFlow API key carries **more than 190 bits of entropy**, so there is no brute-force surface for a slow hash to protect
- Argon2 would add **50-100 ms to every authenticated request** for no security gain
- Keys use HMAC-SHA256 under a server-side pepper, compared with `hmac.compare_digest`: constant time, sub-millisecond
- Passwords are low-entropy and human-chosen, so they **do** use Argon2id
- More: [`docs/security/api-keys.md`](docs/security/api-keys.md)

### The credential boundary

- The upstream SerpApi credential is decrypted in **exactly one place**: the executor, immediately before an upstream call
- It is **never**:
  - decrypted in an API handler
  - attached to a model
  - written to a log
  - present as a field in any Pydantic response schema
- **A test enforces the schema rule:** it walks every model in `app/schemas` and fails if `api_key`, `secret`, `ciphertext` or `encrypted_dek` appears on a response model
- The field is **absent, not excluded**: excluded fields leak through serialisation bugs
- More: [`docs/security/credentials.md`](docs/security/credentials.md)

### Log redaction

- Every structured log record passes through a **redaction filter**
- It scrubs the message, the formatted arguments, the record attributes and the **exception path**
- It recognises:
  - SerpFlow and SerpApi key formats
  - Groq and OpenAI token formats
  - JWTs
  - `key=value` pairs whose key looks sensitive
- **Why the exception path matters:** that is where credentials actually leak. A handler catches an upstream error whose message echoes the request URL, and the URL contains the key
- `tests/unit/test_security.py` asserts it

## Tenant isolation

Every tenant-scoped table carries an indexed `org_id`, and isolation is enforced **twice**:

1. **Application guards** in `app/api/deps.py`
   - resolve the principal and scope the transaction
   - assert that any resource fetched by id belongs to the caller's organization
   - cross-tenant access returns `404`, not `403`: confirming that an id exists in another organization is itself a leak
2. **PostgreSQL row-level security** on 24 tables
   - every scoped table has a policy keyed on `app.current_org`, set per transaction with `SET LOCAL`
   - an unset value matches nothing, so a query issued without the guard returns **no rows**, not every row

More: [`docs/database/rls.md`](docs/database/rls.md)

## Audit log

- **Append-only at the database level:**
  - a trigger refuses `UPDATE` unconditionally
  - it refuses `DELETE` unless the transaction has set `app.audit_purge`, which only organization deletion does
- **Hash chained:** each entry stores the hash of the previous entry for its organization
  - any insertion, edit or removal shows up as a chain break at a known sequence number
- `GET /v1/audit/verify` walks the chain and reports the first break

## Retention

- **Cached SERPs are not anonymous infrastructure data.** A `google_maps_contributor_reviews` payload is one named person's review history across venues
- Engines declare a `pii_risk` level, and a run inherits the highest level of any of its steps
- Retention follows from that, and both values are configurable per project:

```
standard pii_risk    30 days
pii_risk: high        7 days
```

## Hardening a deployment

The defaults in `.env.example` are **development defaults**, and several are marked `CHANGE ME`. Before deploying:

- Replace `JWT_SECRET`, `API_KEY_PEPPER` and `CREDENTIAL_KEK`
- Move the credential KEK to a managed KMS, or to `age` for self-hosting. The `kek_id` column lets you rotate without re-encrypting everything at once
- Set `ENVIRONMENT=production` and `DEBUG=false`
- Terminate TLS in front of the API, and restrict `CORS_ORIGINS` to the frontend origin
- Enforce request size limits at the reverse proxy too: the application limit is a second line, not the only one
- Keep `.env` out of version control. It is gitignored; keep it that way, and never paste real tokens into issues or logs

More: [`docs/deployment/production.md`](docs/deployment/production.md) · [`docs/security/secrets.md`](docs/security/secrets.md) · [`docs/security/threat-model.md`](docs/security/threat-model.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Contributing](CONTRIBUTING.md) | [README](README.md) | [Changelog](CHANGELOG.md) |
