# Upstream credentials

<p>
  <a href="../README.md#security"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="AES: 256-GCM" src="https://img.shields.io/badge/AES-256--GCM-6E40C9">
  <a href="../../backend/app/core/security.py"><img alt="source: core/security.py" src="https://img.shields.io/badge/source-core%2Fsecurity.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Security](../README.md#security) › **Upstream credentials** · page 27 of 50

**A SerpFlow organization attaches its own SerpApi key.** That key is what an attacker actually wants, and the design treats it that way:

- it is encrypted with a **per-credential data key**
- it is decrypted in **exactly one place per use**
- **no response schema** in the codebase has a field that could carry it

Implementation: [`app/core/security.py`](../../backend/app/core/security.py) · [`app/services/credentials/`](../../backend/app/services/credentials) · [`app/services/executor/service.py`](../../backend/app/services/executor/service.py)

## Envelope encryption

- **Each credential gets its own random AES-256-GCM data encryption key (DEK)**
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
- **Where the KEK comes from:**
  - in a cloud deployment it belongs in a **KMS**, and `_load_kek` becomes a call to it
  - locally it is `CREDENTIAL_KEK`: a base64 32-byte value, or any other string, which is then SHA-256'd to 32 bytes so development needs no ceremony
  - generate a real one with `openssl rand -base64 32`

## The fingerprint

- **The UI has to let an operator tell two credentials apart**
- It shows `sha256(secret)[:8]` and the last four characters. **Never anything reversible**

```
Production SerpApi key    a7f3c2d1 ... 8kQ2    valid     1,847 / 5,000 searches
```

## Where it is decrypted

Three call sites, each about to make an upstream call with the result:

```
app/services/executor/service.py:_decrypt_credential   executing a step
app/services/credentials/service.py:validate           one cheap probe call
app/services/credentials/service.py:reconcile_quota    reading account quota
```

- **The planner never decrypts. The cache layer never decrypts. The API layer never decrypts**
- A plaintext key exists **only for the duration of the call it is about to make**
- The two credential-service paths drop the local reference in a `finally` block, instead of letting it live to the end of the function
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
- **A field that does not exist cannot be serialized by any means.** See [ADR 0006](../adr/0006-no-credential-field-in-schemas.md)

## Never in a log

[`CredentialRedactionFilter`](../../backend/app/core/logging.py) is installed on the root logger and scrubs **four surfaces**, because a secret reaches a log record by more than one route:

1. `record.msg`
2. `record.args`, tuple or dict
3. arbitrary attributes passed through `extra=`
4. `record.exc_info`, where a traceback can carry local variables

- **Patterns covered:**
  - anything shaped like a SerpApi key, or a SerpFlow key
  - the values of keys named `api_key`, `serpapi_key`, `password`, `secret`, `token`, `authorization` or `ciphertext`
- **Tested, not assumed** ([`tests/unit/test_security.py`](../../backend/tests/unit/test_security.py)):
  - a key is pushed through each of the four routes, and the emitted record is asserted not to contain it
  - the same file asserts `CredentialResponse` has no field able to hold a secret, by inspecting `model_fields`

## Validation and revocation

```http
POST /v1/credentials/{id}/validate
```

- **One cheap upstream call**, recording `validation_status` plus the reported quota
- **On failure, only the exception class name is stored:** provider error messages have been known to echo the key back

```http
POST /v1/credentials/{id}/rotate
```

- Encrypts the new secret, points the organization default at it, marks the old one revoked
- **Opens a grace window** (`grace_until`, 15 minutes by default): both decrypt during it, so in-flight runs finish
- **Once the window closes**, `destroy_expired_rotations` blanks the old `ciphertext` and `encrypted_dek`. The row survives for audit; the secret does not

```http
DELETE /v1/credentials/{id}
```

- **An immediate revoke:** skips the grace window, and erases the ciphertext in the same transaction

Bulk operations:

```http
POST /v1/credentials/revalidate         re-check every credential
POST /v1/credentials/reconcile-quota    refresh upstream quota snapshots
```

## Revoked mid-run

- **`_assert_credential_still_valid` re-checks before every upstream call**, not once at the start
- A credential revoked while a run is in flight raises **`CREDENTIAL_REVOKED`** and fails the run
- **It does not return the hops that happened to finish first:** a partial result that looks complete is worse than an error, because a caller will act on it

## What is audited

- **Every credential operation writes an audit entry:** create, validate, rotate, delete, and attach-to-project
- The entry records the **actor**, the **credential id** and the **fingerprint**
- It **never** records the ciphertext or the secret

## Related

- [Bring your own key](byok.md): which keys you supply, and what happens without them
- [API keys](api-keys.md): the other half of the credential story
- [Secrets](secrets.md): every secret the service holds
- [ADR 0005: envelope encryption](../adr/0005-envelope-encryption.md)
- [Threat model](threat-model.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Bring your own key](../security/byok.md) | [Docs index](../README.md) | [API keys](../security/api-keys.md) |
