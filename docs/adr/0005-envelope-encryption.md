# 0005. Envelope encryption for upstream credentials

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0005. Envelope encryption for upstream credentials** · page 41 of 50

**Status** Accepted

## Context

- **SerpFlow holds its customers' SerpApi keys**
- Unlike a password or an API key, this secret must be **recoverable**: the executor needs the plaintext to make the upstream call. Hashing is not an option
- **So it must be encrypted**, and the question is **what** encrypts it
- **The naive answer is one key for everything:** a single `ENCRYPTION_KEY`, AES-GCM, done
  - that works until the key must be rotated, when **every ciphertext** in the system has to be decrypted and re-encrypted

## Decision

**Envelope encryption.**

- **Each credential gets its own random AES-256-GCM data encryption key (DEK)**
- The DEK encrypts the secret; a **key encryption key (KEK)** wraps the DEK
- **Only the wrapped DEK is stored**

```python
dek        = AESGCM.generate_key(bit_length=256)
ciphertext = AESGCM(dek).encrypt(os.urandom(12), secret.encode(), None)
wrapped    = AESGCM(kek).encrypt(os.urandom(12), dek, None)
```

- **Stored:** `ciphertext`, `encrypted_dek`, `kek_id`, `algo`, `fingerprint`
- **`kek_id` is what makes rotation tractable**
  - rotating the KEK means unwrapping and rewrapping each DEK; the ciphertext itself never moves
  - cost is proportional to the **number of credentials**, not the volume of encrypted data
- **Where the KEK lives:** the process environment locally; a **KMS** in production, where `_load_kek` becomes a call to it. That boundary is already where it needs to be
- **Alongside it, a non-reversible fingerprint** (`sha256(secret)[:8]`), so the UI can tell two credentials apart without anything reversible reaching a response

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

## See also

- [Upstream credentials](../security/credentials.md)
- [Secrets](../security/secrets.md)
- [ADR 0006: no credential field in schemas](0006-no-credential-field-in-schemas.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0004: HMAC-SHA256 for API keys, Argon2id for p…](../adr/0004-hmac-for-api-keys.md) | [Docs index](../README.md) | [ADR 0006: The credential field is absent from sche…](../adr/0006-no-credential-field-in-schemas.md) |
