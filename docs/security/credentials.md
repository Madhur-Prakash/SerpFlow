# Upstream credentials

<p>
  <a href="../security/README.md"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="AES: 256-GCM" src="https://img.shields.io/badge/AES-256--GCM-6E40C9">
  <a href="../../backend/app/core/security.py"><img alt="source: core/security.py" src="https://img.shields.io/badge/source-core%2Fsecurity.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 9 min" src="https://img.shields.io/badge/read-9%20min-555555">
</p>

[Docs](../README.md) › [Security](../security/README.md) › **Upstream credentials** · page 41 of 57

**A SerpFlow organization attaches its own SerpApi key**, and optionally a Groq key ([bring your own key](byok.md)). That key is what an attacker actually wants, and the design treats it that way:

- it is encrypted with a **per-credential data key** ([ADR 0003](../adr/0003-envelope-encryption.md))
- it is decrypted only **at the point of use**, for the call about to be made
- **no response schema** in the codebase has a field that could carry it

Implementation: [`app/core/security.py`](../../backend/app/core/security.py) · [`app/services/credentials/`](../../backend/app/services/credentials) · [`app/services/executor/service.py`](../../backend/app/services/executor/service.py) · table: [`upstream_credentials`](../database/schema.md#upstream_credentials)

## Envelope encryption

- **Each credential gets its own random AES-256-GCM data encryption key (DEK)**, whichever provider it is for
- The DEK encrypts the secret; the **KEK** encrypts the DEK
- **Only the wrapped DEK is stored**

```python
dek = AESGCM.generate_key(bit_length=256)
ciphertext = AESGCM(dek).encrypt(os.urandom(12), secret.encode(), None)
wrapped    = AESGCM(kek).encrypt(os.urandom(12), dek, None)
```

Stored columns:

| Column | Holds |
| --- | --- |
| `ciphertext` | nonce + AES-256-GCM ciphertext, base64 |
| `encrypted_dek` | nonce + the wrapped DEK, base64 |
| `kek_id` | which KEK wrapped it, so rotation is possible |
| `algo` | `AES-256-GCM/DEK+KEK` |
| `fingerprint` | `sha256(secret)[:8]` |

- **Rotating the KEK** means unwrapping each DEK and rewrapping it
  - the ciphertext itself does not move: that is the point of the envelope
  - cost is proportional to the **number of credentials**, not the volume of data. Procedure: [secrets: KEK rotation](secrets.md#kek)
  - **no tooling ships for it yet:** `kek_id` is recorded on every row, but `_load_kek` reads one `CREDENTIAL_KEK` and `decrypt_credential` does not consult `kek_id`
- **Where the KEK comes from:**
  - in a cloud deployment it belongs in a **KMS**, and `_load_kek` becomes a call to it
  - locally it is [`CREDENTIAL_KEK`](secrets.md#inventory): a base64 32-byte value, or any other string, which is then SHA-256'd to 32 bytes so development needs no ceremony
  - generate a real one with `openssl rand -base64 32`

## The fingerprint

- **The UI has to let an operator tell two credentials apart**
- It shows `sha256(secret)[:8]`, and a `display` of `...` plus the **last four characters of that fingerprint**, not of the key. **Never anything reversible** ([`public_view`](../../backend/app/services/credentials/service.py))

```
Production SerpApi key    a7f3c2d1    ...c2d1    valid     1,847 searches left
```

- **The fingerprint also refuses duplicates:** attaching a key whose fingerprint matches a live credential in the same organization fails with `CONFLICT`

## Where it is decrypted

Four call sites, each about to make an upstream call with the result:

```
app/services/executor/service.py:_decrypt_credential   executing a step (SerpApi)
app/services/credentials/service.py:validate           one cheap probe call (either provider)
app/services/credentials/service.py:reconcile_quota    reading account quota (SerpApi)
app/services/credentials/llm.py:resolve_llm            planning with the organization's Groq key
```

- **The cache layer never decrypts. The API layer never decrypts.** The planner never decrypts a SerpApi key; it receives a Groq adapter that `resolve_llm` built for this one request ([planner: which adapter plans](../architecture/planner.md#which-adapter-plans))
- **The executor decrypts once per run**, and only in `live` or `record` mode ([executor: the credential boundary](../architecture/executor.md#the-credential-boundary))
- A plaintext key exists **only for the duration of the work it is about to do**
- The two credential-service paths drop the local reference in a `finally` block, instead of letting it live to the end of the function
- **A Groq key that cannot be decrypted** (a changed KEK, a corrupted row) does not fail planning: `resolve_llm` logs `llm.credential_undecryptable` and plans deterministically
- **Everything else that needs to talk about a credential uses the fingerprint**

## Never in a response

**The field must be absent from the schema**, not present-and-excluded:

```python
# app/schemas/identity.py
class CredentialResponse(APIModel):
    id: str
    name: str
    provider: str
    fingerprint: str              # sha256(secret)[:8]
    display: str                  # ...a3f9
    kek_id: str
    algo: str
    validation_status: str
    ...
    # There is deliberately no api_key, secret or ciphertext field here.
    # Not exclude=True, not SecretStr - absent.
```

- **`exclude=True` is a serialization setting.** Settings get changed, overridden by `model_dump(exclude=None)`, or forgotten in a subclass
- **A field that does not exist cannot be serialized by any means.**
- **Every credential response is built by `public_view`**, which has no code path that could emit the secret ([`app/api/v1/credentials.py`](../../backend/app/api/v1/credentials.py))

## Never in a log

[`CredentialRedactionFilter`](../../backend/app/core/logging.py) is installed on the root logger and on every handler, and scrubs **four surfaces**, because a secret reaches a log record by more than one route:

1. `record.msg`
2. `record.args`, tuple or dict
3. arbitrary attributes passed through `extra=`
4. `record.exc_info` and `record.exc_text`, where an exception message can carry the key

- **Patterns covered:**
  - anything shaped like a SerpFlow key, a SerpApi key (64 hex characters), a Groq `gsk_` key, an `sk-` token or a JWT
  - `name=value` and `"name": "value"` pairs for sensitive-looking names: `api_key`, `serpapi_key`, `password`, `secret`, `token`, `authorization`, `bearer`, `credential`, `encrypted_dek`, `dek`, `kek`, `pepper`, `private_key`
  - mapping values under keys such as `api_key`, `password`, `token`, `ciphertext`, `encrypted_dek`, `key_hash` and `payload`
- **Audit `before` / `after` bodies** go through the same `redact_mapping` before they are written and hashed
- **Tested, not assumed** ([`tests/unit/test_security.py`](../../backend/tests/unit/test_security.py)):
  - SerpFlow, SerpApi, `gsk_` and `sk-` keys are scrubbed from free text and from nested mappings
  - a key passed through `record.args`, and a `"api_key": "..."` pair inside `record.msg`, are asserted absent from the formatted message
  - the `extra=` and `exc_info` routes are implemented in the filter but have no dedicated test yet
  - the same file asserts `CredentialResponse` has no field able to hold a secret, and walks **every** response model in `app/schemas` for forbidden field names

## Validation and revocation

Endpoints and the permission each needs ([API: identity and access](../api/overview.md#identity-and-access)):

| Endpoint | Permission | What it does |
| --- | --- | --- |
| `POST /v1/credentials` | `credential:write` | encrypt, validate (unless `validate_now` is false), store |
| `POST /v1/credentials/{id}/validate` | `credential:write` | one probe call now |
| `POST /v1/credentials/{id}/rotate` | `credential:rotate` | replace the secret, with a grace window |
| `DELETE /v1/credentials/{id}` | `credential:rotate` | revoke immediately |
| `POST /v1/credentials/revalidate` | `credential:write` | queue a re-check of every credential |
| `POST /v1/credentials/reconcile-quota` | `credential:read` | queue a quota reconciliation |

`credential:rotate` belongs to the owner alone; `credential:write` to admins and owners ([roles](api-keys.md#roles)).

```http
POST /v1/credentials/{id}/validate
```

- **One cheap upstream call** that spends nothing: SerpApi's account endpoint, or Groq's model list. It records `validation_status`, and for SerpApi the reported plan and searches left
- **On failure, only the exception class name is kept:** provider error messages have been known to echo the key back
- **Where a failure lands depends on the path:**
  - through the API, the request fails with `CREDENTIAL_VALIDATION_FAILED` (422) and the transaction rolls back. On `POST /v1/credentials` that means **a key the provider rejects is never stored**; on `.../validate` the stored status is left as it was
  - the background re-check catches the failure, so `validation_status = failed` and the class name in `validation_error` persist, and an alert is raised

```http
POST /v1/credentials/{id}/rotate
```

- **Encrypts and validates the new secret first**, then moves every pointer in one transaction: each project whose `credential_id` named the old credential, and the organization default if it did (SerpApi only)
- **Marks the old one revoked and opens a grace window** (`grace_until`, `grace_minutes`, 15 by default, at most 1,440): the old one stays usable during it, so in-flight runs finish
- **After the window, the old credential is unusable but its envelope stays at rest.** `CredentialService.destroy_expired_rotations` would blank its `ciphertext` and `encrypted_dek`, keeping the row for audit, but nothing calls it at HEAD. `DELETE` the old credential to erase it

```http
DELETE /v1/credentials/{id}
```

- **An immediate revoke:** skips the grace window, and erases the ciphertext in the same transaction
- **Projects and the organization default keep pointing at it.** Resolution skips a revoked credential and falls through to the next pointer, then to `NO_UPSTREAM_CREDENTIAL` ([troubleshooting](../operations/troubleshooting.md#no_upstream_credential))
- **A new credential does not replace a revoked default on its own:** it becomes the default automatically only when the organization has none, and the revoked pointer still counts. Pass `set_as_org_default: true`

Bulk operations go through Kafka ([topics](../operations/kafka.md#topics)), and answer `ok: false` when Kafka is unavailable rather than doing the work inline:

```http
POST /v1/credentials/revalidate         serpflow.credentials.validate: re-check every credential
POST /v1/credentials/reconcile-quota    serpflow.quota.reconcile: refresh upstream quota snapshots
```

- **A failed background validation adds a critical `credential.validation_failed` alert**, with a per-credential `dedupe_key`
- **Reconciliation writes an [`upstream_quota_snapshots`](../database/schema.md#upstream_quota_snapshots) row**, with the divergence between SerpFlow's ledger and SerpApi's own count. They differ the moment the key is used outside SerpFlow

## Revoked mid-run

- **`_assert_credential_still_valid` re-checks before every upstream call**, not once at the start ([executor: revocation mid-run](../architecture/executor.md#revocation-mid-run))
- A credential that is revoked and past its grace window raises **`CREDENTIAL_REVOKED`** (409) and fails the run
- **It does not return the hops that happened to finish first:** a partial result that looks complete is worse than an error, because a caller will act on it
- **The check reads the credential row the executor loaded at the start of the run**; it does not re-query the database. It reliably catches a rotation's grace window closing mid-run; a revocation committed by another request during the run is not re-read
- [Troubleshooting: `CREDENTIAL_REVOKED` part-way through a run](../operations/troubleshooting.md#credential_revoked-part-way-through-a-run)

## What is audited

| Action | Written by | Records |
| --- | --- | --- |
| `credential.created` | `POST /v1/credentials` | name, provider, fingerprint |
| `credential.rotated` | `POST /v1/credentials/{id}/rotate` | old and new credential ids, new fingerprint, grace minutes |
| `credential.revoked` | `DELETE /v1/credentials/{id}` | fingerprint |
| `project.updated` | `PATCH /v1/projects/{id}` | the `credential_id` before and after, when a project is attached |

- Each entry records the **actor**, the **credential id** and, where one exists, the **fingerprint**
- It **never** records the ciphertext or the secret
- **Validation is not audited.** Its outcome lives on the credential (`validation_status`, `validation_error`, `last_validated_at`), and a background failure raises an alert instead
- The log itself: [row-level security: the audit log](../database/rls.md#the-audit-log)

## Related

- [Bring your own key](byok.md): which keys you supply, and what happens without them
- [API keys](api-keys.md): the other half of the credential story
- [Secrets](secrets.md#kek): the KEK, and what rotating it involves
- [ADR 0003: envelope encryption](../adr/0003-envelope-encryption.md): why a per-credential DEK under a KEK
- [Executor: the credential boundary](../architecture/executor.md#the-credential-boundary): where a run decrypts, and when
- [Threat model](threat-model.md#credential-theft-from-the-database): the threats this page answers
- [Troubleshooting: `NO_UPSTREAM_CREDENTIAL`](../operations/troubleshooting.md#no_upstream_credential): a live key with nothing attached
- [Observability: logging](../operations/observability.md#logging): the redaction that keeps keys out of logs

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Bring your own key](../security/byok.md) | [Docs index](../README.md) · [Security index](../security/README.md) | [API keys](../security/api-keys.md) |
