# 0003. Envelope encryption for upstream credentials

<p>
  <a href="../adr/README.md"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/services/credentials/llm.py"><img alt="source: credentials/llm.py" src="https://img.shields.io/badge/source-credentials%2Fllm.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 4 min" src="https://img.shields.io/badge/read-4%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../adr/README.md) › **0003. Envelope encryption for upstream credentials** · page 56 of 65

**Status** Accepted

## Context

- **SerpFlow holds its customers' [SerpApi keys](../security/byok.md)**
- Unlike a password or an API key, this secret must be **recoverable**: the [executor](../architecture/executor.md#the-credential-boundary) needs the plaintext to make the upstream call. Hashing is not an option
- **So it must be encrypted**, and the question is **what** encrypts it
- **The naive answer is one key for everything:** a single `ENCRYPTION_KEY`, AES-GCM, done
  - that works until the key must be rotated, when **every ciphertext** in the system has to be decrypted and re-encrypted

## Decision

**[Envelope encryption](../security/credentials.md#envelope-encryption).**

- **Each credential gets its own random AES-256-GCM data encryption key (DEK)**
- The DEK encrypts the secret; a **key encryption key (KEK)** wraps the DEK
- **Only the wrapped DEK is stored**

```python
# app/core/security.py: encrypt_credential, simplified
dek        = AESGCM.generate_key(bit_length=256)
ciphertext = AESGCM(dek).encrypt(os.urandom(12), secret.encode(), None)
wrapped    = AESGCM(kek).encrypt(os.urandom(12), dek, None)
```

- **Stored** on [`upstream_credentials`](../database/schema.md#upstream_credentials): `ciphertext`, `encrypted_dek`, `kek_id`, `algo`, `fingerprint`
- **`kek_id` is what makes rotation tractable**
  - rotating the KEK means unwrapping and rewrapping each DEK; the ciphertext itself never moves
  - cost is proportional to the **number of credentials**, not the volume of encrypted data
- **Where the KEK lives:** the process environment locally ([`CREDENTIAL_KEK`](../security/secrets.md#inventory)); a **KMS** in production, where `_load_kek` becomes a call to it. That boundary is already where it needs to be
- **Alongside it, a non-reversible [fingerprint](../security/credentials.md#the-fingerprint)** (`sha256(secret)[:8]`), so the UI can tell two credentials apart without anything reversible reaching a response

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **One key for everything** | Simpler, but rotation becomes a full re-encryption of every row. And one compromised key exposes every credential, with no per-credential boundary at all |
| **PostgreSQL `pgcrypto`** | Puts the key in the database or in a query parameter, so it reaches the query log. The thing being protected ends up next to the thing it is protected from |
| **KMS per-operation encryption** | A network call on every decrypt, in the execution path. Envelope encryption keeps KMS **out of the hot path**: the KEK loads once, and the DEK unwrap is local |

## Cost

- **More moving parts:** two keys, two nonces, a `kek_id`, and a rotation procedure that has to be written down rather than inferred. See [secrets: KEK](../security/secrets.md#kek)
- **The honest limit:** with the process environment, an attacker has the KEK
  - envelope encryption defends against a **database dump**, not against a **compromised host**
  - that boundary is stated explicitly in [the threat model](../security/threat-model.md#out-of-scope), not left implied
- **Update (2026-10-11): what the vault holds, and what rotation still needs**
  - **Every provider's key, not only SerpApi's:** organizations also bring a Groq key for planning ([bring your own key](../security/byok.md#where-the-keys-live)); it goes through the same envelope and is decrypted only in `resolve_llm` ([`credentials/llm.py`](../../backend/app/services/credentials/llm.py))
  - **`kek_id` is recorded but does not yet choose a key:** `_load_kek` reads the single `CREDENTIAL_KEK`, and `decrypt_credential` takes no `kek_id` ([`app/core/security.py`](../../backend/app/core/security.py)). So today a rotation is an offline re-wrap with the services stopped ([secrets: KEK](../security/secrets.md#kek)); keeping the old and new KEKs side by side for a live rotation needs that lookup added first. The decision stands; the tooling for it is not built

## Related

- [Upstream credentials: envelope encryption](../security/credentials.md#envelope-encryption): the scheme as implemented, with validation, revocation and audit
- [Secrets: KEK](../security/secrets.md#kek): custody of `CREDENTIAL_KEK` and the rewrap procedure
- [Threat model: credential theft from the database](../security/threat-model.md#credential-theft-from-the-database): the dump this defends against, and the compromised host it does not
- [Executor: the credential boundary](../architecture/executor.md#the-credential-boundary): where the plaintext is decrypted to run a step, and zeroed after it
- [`test_security.py`](../../backend/tests/unit/test_security.py): round-trip, per-credential DEK, no plaintext in the ciphertext, short non-reversible fingerprint
- [Database schema: `upstream_credentials`](../database/schema.md#upstream_credentials): every stored column, none holding a recoverable key

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0004: HMAC-SHA256 for API keys, Argon2id for p…](../adr/0004-hmac-for-api-keys.md) | [Docs index](../README.md) · [Architecture decision records](../adr/README.md) | [ADR 0006: The credential field is absent from sche…](../adr/0006-no-credential-field-in-schemas.md) |
