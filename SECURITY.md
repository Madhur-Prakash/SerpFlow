# Security policy

<p>
  <a href="#reporting-a-vulnerability"><img alt="reporting: public issues" src="https://img.shields.io/badge/reporting-public%20issues-2F6BFF?logo=github&logoColor=white"></a>
  <a href="README.md#hosting"><img alt="hosting: self-hosted, for now" src="https://img.shields.io/badge/hosting-self--hosted%2C%20for%20now-555555"></a>
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
- **It is self-hosted, for now, by the author's decision.** There is no public hosted instance, so every deployment is run by its own operator, who is responsible for it
  - **the author will host SerpFlow on demand**, once enough people ask for it: [hosting](README.md#hosting)
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
- Thank you for reporting carefully. It matters more on a project with one maintainer, not less
- What is defended, and what is deliberately out of scope: [threat model](docs/security/threat-model.md#out-of-scope)

## Reporting a vulnerability

- **Open a public GitHub issue** on [this repository](https://github.com/Madhur-Prakash/SerpFlow/issues). That is the author's chosen channel; there is no private one
- **Why public works here:** SerpFlow is self-hosted, so the author runs no instance holding other people's data, and an open report lets every operator see a problem and its fix at the same time
- **Keep the report safe to publish.** Never include:
  - real API keys, passwords, tokens, `API_KEY_PEPPER`, `JWT_SECRET` or `CREDENTIAL_KEK` values
  - a SerpApi or Groq key, even a revoked one
  - the address of a deployment that is not yours, or anyone's personal data
- **Reproduce it against a local instance** (`make up && make seed`, a `sf_test_...` key), and describe that
- Include:
  - what you did
  - what happened
  - what you expected
  - a proof of concept, if you have one, against your own local instance
- **If a real secret was exposed**, rotate it first, then report: [rotation](docs/security/secrets.md#rotation)
- You will get a reply on the issue, then updates while a fix is worked on
- **Running SerpFlow yourself?** Watch the repository's issues and releases: fixes land on `main` and in `1.0.x` patch releases
- **Do not run automated scanners** against a deployment you do not own

## Supported versions

| Version | Supported |
| --- | --- |
| `main` | Yes: security fixes land here |
| `1.0.x` | Yes: the current release; fixes ship as `1.0.x` patch releases |
| `0.1.0` and earlier | No: upgrade to `1.0.x` |

## What SerpFlow holds

SerpFlow is a control plane for a paid upstream API, so it holds sensitive material of four kinds ([assets](docs/security/threat-model.md#assets)):

| Material | Where it lives | Protection |
| --- | --- | --- |
| Upstream SerpApi and Groq credentials, brought by each organization ([BYOK](docs/security/byok.md)) | `upstream_credentials` | Envelope encryption: a random per-credential AES-256-GCM data key, wrapped by a key-encryption key. Only the ciphertext and the wrapped key are stored |
| SerpFlow API keys | `api_keys` | HMAC-SHA256 under a server-side pepper. The plaintext is shown once, at creation, and never again |
| User passwords | `users` | Argon2id, `time_cost=3`, `memory_cost=64MiB`, `parallelism=4` |
| Cached SERP payloads | object storage | Content-addressed, referenced by `payload_ref`. Shorter retention for high-PII-risk engines |

### Why API keys are not Argon2-hashed

- **A deliberate decision, not an oversight**
- A SerpFlow API key carries **more than 190 bits of entropy**, so there is no brute-force surface for a slow hash to protect
- Argon2 would add **50-100 ms to every authenticated request** for no security gain
- Keys use HMAC-SHA256 under a server-side pepper, compared with `hmac.compare_digest`: constant time, sub-millisecond
- Passwords are low-entropy and human-chosen, so they **do** use Argon2id
- **The pepper (`API_KEY_PEPPER`) never enters the database**, so a dump alone cannot verify a guessed key
- More: [`docs/security/api-keys.md`](docs/security/api-keys.md#hashing-hmac-sha256-not-argon2)

### The credential boundary

- An upstream credential is decrypted **only immediately before an upstream call**, and the plaintext never outlives the request:
  - the SerpApi key in the executor, for a search, and in the credential service, for its validation and quota probes
  - a Groq key in `resolve_llm`, which hands it straight to the planner's adapter
- It is **never**:
  - decrypted in an API handler
  - attached to a model
  - written to a log
  - present as a field in any Pydantic response schema
- **A test enforces the schema rule:** it walks every model in `app/schemas` and fails if `api_key`, `secret`, `ciphertext` or `encrypted_dek` appears on a response model
- The field is **absent, not excluded**: excluded fields leak through serialisation bugs
- More: [`docs/security/credentials.md`](docs/security/credentials.md#where-it-is-decrypted) · [ADR 0003: envelope encryption](docs/adr/0003-envelope-encryption.md)

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
- More: [credentials: never in a log](docs/security/credentials.md#never-in-a-log) · [observability: logging](docs/operations/observability.md#logging)

## Tenant isolation

Every tenant-scoped table carries an indexed `org_id`, and isolation is enforced **twice**:

1. **Application guards** in `app/api/deps.py`
   - resolve the principal and scope the transaction
   - assert that any resource fetched by id belongs to the caller's organization
   - cross-tenant access returns `404`, not `403`: confirming that an id exists in another organization is itself a leak
2. **PostgreSQL row-level security** on 24 tables
   - every scoped table has a policy keyed on `app.current_org`, set per transaction with `SET LOCAL`
   - **an unset value matches every row, deliberately:** migrations, the seed and cross-organization workers run without a tenant. Every request path sets it, because the principal cannot resolve without doing so
   - want the strict posture? Drop that clause and give those paths a role with `BYPASSRLS`: [the empty-value clause](docs/database/rls.md#the-empty-value-clause)

More: [`docs/database/rls.md`](docs/database/rls.md) · [ADR 0006](docs/adr/0006-rls-plus-application-guards.md)

## Audit log

- **Append-only at the database level:**
  - a trigger refuses `UPDATE` unconditionally
  - it refuses `DELETE` unless the transaction has set `app.audit_purge`, which only the demo seed's reset does today; it is reserved for organization deletion, which has no endpoint yet
- **Hash chained:** each entry stores the hash of the previous entry for its organization
  - any insertion, edit or removal shows up as a chain break at a known sequence number
- `GET /v1/audit/verify` walks the chain and reports the first break
- More: [row-level security: the audit log](docs/database/rls.md#the-audit-log)

## Retention

- **Cached SERPs are not anonymous infrastructure data.** A `google_maps_contributor_reviews` payload is one named person's review history across venues
- Engines declare a `pii_risk` level, and a run inherits the highest level of any of its steps
- Retention follows from that, and each run records it as its `expires_at`:

```
standard pii_risk    30 days    RETENTION_STANDARD_DAYS
pii_risk: high        7 days    RETENTION_HIGH_PII_DAYS
```

- **Both are instance-wide.** A project can store its own `retention_days` and `retention_high_pii_days`, but the executor does not apply them yet ([`executor/service.py`](backend/app/services/executor/service.py))
- **Nothing deletes an expired run or payload automatically yet:** purging rows past `expires_at`, and their objects in storage, is an operator task
- Raw payloads also sit behind their own permission, `payload:read`. More: [threat model: personal data](docs/security/threat-model.md#personal-data-in-cached-payloads)

## Hardening a deployment

The defaults in `.env.example` are **development defaults**, and several are marked `CHANGE ME`. Before deploying:

- Replace `JWT_SECRET`, `API_KEY_PEPPER` and `CREDENTIAL_KEK`
- Move the credential KEK to a managed KMS, or to `age` for self-hosting. The `kek_id` column lets you rotate without re-encrypting everything at once
- Set `ENVIRONMENT=production` and `DEBUG=false`
- Terminate TLS in front of the API, and restrict `CORS_ORIGINS` to the frontend origin
- Enforce request size limits at the reverse proxy too: the application limit is a second line, not the only one
- Keep `.env` out of version control. It is gitignored; keep it that way, and never paste real tokens into issues or logs
- Connect the application as a database role that does not own the tables, or set `FORCE ROW LEVEL SECURITY`: a table owner bypasses row-level security
- Leave `LLM_PROVIDER=groq` and `GROQ_API_KEY` unset on an instance other people use: otherwise your Groq key answers for every organization that has not brought one ([BYOK: the self-hosting exception](docs/security/byok.md#the-self-hosting-exception))
- `SEED_ON_STARTUP` is refused once `ENVIRONMENT` is `staging` or `production`, because the demo accounts' password is committed to this repository ([bootstrap](docs/operations/bootstrap.md#3-an-environment-refusal))

More: [`docs/deployment/production.md`](docs/deployment/production.md#before-anything-else) · [`docs/security/secrets.md`](docs/security/secrets.md#production-checklist) · [`docs/security/threat-model.md`](docs/security/threat-model.md) · [deployment guide](docs/deployment/deployment-guide.md#pre-launch-checklist)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Contributing](CONTRIBUTING.md) | [README](README.md) | [Changelog](CHANGELOG.md) |
