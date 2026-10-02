# 0005. Envelope encryption for upstream credentials

**Status** Accepted

## Context

SerpFlow holds its customers' SerpApi keys. Unlike a password or an API key,
this one has to be **recoverable** — the executor needs the plaintext to make
the upstream call. Hashing is not an option.

So it must be encrypted, and the question is what encrypts it.

The naive answer is one key for everything: a single `ENCRYPTION_KEY`, AES-GCM,
done. That works until the key has to be rotated, at which point every
ciphertext in the system has to be decrypted and re-encrypted.

## Decision

Envelope encryption. Each credential gets its own random AES-256-GCM data
encryption key; the DEK encrypts the secret; a key encryption key wraps the
DEK. Only the wrapped DEK is stored.

```python
dek        = AESGCM.generate_key(bit_length=256)
ciphertext = AESGCM(dek).encrypt(os.urandom(12), secret.encode(), None)
wrapped    = AESGCM(kek).encrypt(os.urandom(12), dek, None)
```

Stored: `ciphertext`, `encrypted_dek`, `kek_id`, `algo`, `fingerprint`.

`kek_id` is what makes rotation tractable. Rotating the KEK means unwrapping
and rewrapping each DEK; the ciphertext itself never moves. Cost is
proportional to the number of credentials, not the volume of encrypted data.

The KEK lives in the process environment locally and belongs in a KMS in
production, where `_load_kek` becomes a call to it. That boundary is already
where it needs to be.

Alongside it, a non-reversible fingerprint — `sha256(secret)[:8]` — so the UI
can distinguish two credentials without anything reversible reaching a
response.

## Alternatives rejected

**One key for everything.** Simpler, and rotation becomes a full re-encryption
of every row. Also: one compromised key exposes every credential, with no
per-credential boundary at all.

**PostgreSQL `pgcrypto`.** Puts the key in the database or in a query
parameter, which means it reaches the query log. The thing being protected ends
up adjacent to the thing it is being protected from.

**KMS per-operation encryption.** A network call on every credential decrypt,
in the execution path. Envelope encryption is the standard answer precisely
because it keeps KMS out of the hot path — the KEK is loaded once, the DEK
unwrap is local.

## Cost

More moving parts: two keys, two nonces, a `kek_id`, and a rotation procedure
that has to be written down rather than inferred.

And the honest limit: with the process environment, an attacker has the KEK.
Envelope encryption defends against a database dump, not against a compromised
host. That boundary is stated explicitly in
[the threat model](../security/threat-model.md) rather than left implied.

## See also

- [Upstream credentials](../security/credentials.md)
- [Secrets](../security/secrets.md)
- [ADR 0006 — no credential field in schemas](0006-no-credential-field-in-schemas.md)
