# Secrets

Every secret the service holds, where it lives, and what happens if it leaks.
Configuration is entirely environment driven; see
[`.env.example`](../../.env.example) for the authoritative list and
[`app/core/config.py`](../../backend/app/core/config.py) for the types.

## Inventory

| Secret | Variable | Protects | If it leaks |
| --- | --- | --- | --- |
| KEK | `CREDENTIAL_KEK` | every upstream SerpApi credential | rotate the KEK, rewrap every DEK |
| API key pepper | `API_KEY_PEPPER` | the API key hashes | every key must be rotated |
| JWT secret | `JWT_SECRET` | browser sessions | sessions are forgeable; rotate, all users re-login |
| Database password | `DATABASE_URL` | everything at rest | rotate and re-check network exposure |
| S3 credentials | `S3_SECRET_ACCESS_KEY` | stored SERP payloads | rotate; payloads are content-addressed, not secret by themselves |
| Webhook secrets | per channel, hashed | delivery authenticity | per-channel rotation only |
| Groq key | `GROQ_API_KEY` | the planner's language model | upstream billing only; no SerpFlow data at risk |
| SerpApi key | encrypted in the vault | upstream spend | see [credentials](credentials.md) |

Blast radii are deliberately different sizes. A leaked JWT secret costs every
user a re-login; a leaked pepper costs every API key. That is why the two are
separate values rather than one `SECRET_KEY` reused everywhere, which is the
common shortcut and the reason one leak usually means total compromise.

## Where they are not

- **Not in the database.** The pepper and the KEK are process environment only.
  A database dump is not sufficient to verify a guessed API key or to decrypt a
  credential.
- **Not in the repository.** `.env` is gitignored; `.env.example` holds only
  obvious placeholders, each marked `CHANGE ME`.
- **Not in a log.** `CredentialRedactionFilter` is installed on the root logger
  and scrubs message, args, `extra=` attributes and the exception path.
- **Not in an error response.** Errors carry a stable code, a sentence, and a
  request id. Never a stack trace, never a configuration value.
- **Not in a response schema.** There is no field anywhere in `app/schemas`
  that could carry a credential, and a test asserts it by walking every
  response model rather than by inspection.

## Local development

The defaults in `.env.example` are deliberately working values, because
`make dev` and `make seed` must work with **no keys at all**. The local KEK is
a published base64 string; the pepper and JWT secret both say
`change-me-...-local-dev-only`.

This is a trade. A setup that demands four secrets before it will boot gets
them generated badly, or shared. A setup that boots with obvious placeholders
makes the danger visible: the string `change-me-in-production` in a production
environment is grep-able, alarming, and easy to catch in review.

With no keys at all you get:

- `LLM_PROVIDER=mock` — deterministic planning, no network
- `SERPFLOW_MODE=replay` — cassettes only, never the network
- `sf_test_...` keys — deterministic mock results, zero SerpApi credits

## Generating real ones

```bash
# 32-byte KEK, base64
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"

# pepper and JWT secret
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Each value should be distinct, and should come from a secret manager rather
than a file, in any environment that is not a laptop.

## Rotation

### KEK

Envelope encryption is what makes this cheap. Only the wrapped DEKs change; the
ciphertext does not move.

1. Add the new KEK alongside the old, keyed by `kek_id`.
2. For each credential: unwrap the DEK with the old KEK, rewrap with the new,
   update `encrypted_dek` and `kek_id`.
3. Remove the old KEK once no row references its id.

Cost is proportional to the number of credentials, not to the volume of
encrypted data.

### Pepper

The pepper is an input to the hash, so rotating it invalidates every stored
hash. There is no re-peppering without the plaintext, and the plaintext is
gone by design. Rotating the pepper means rotating every API key:

1. Mint replacements under the new pepper.
2. Distribute them, using the rotation grace window.
3. Switch the pepper and revoke the old keys.

Plan for this before you need it. It is the most disruptive rotation in the
system, which is the correct trade for a value that never has to be read back.

### JWT secret

Sessions signed with the old secret stop verifying, so every user is logged
out. Access tokens live 15 minutes and refresh tokens 14 days; rotating the
secret cuts both immediately. For a planned rotation, accept both secrets for
one refresh-token lifetime, then drop the old one.

## Production checklist

- [ ] `ENVIRONMENT=production` and `DEBUG=false`
- [ ] `JWT_SECRET`, `API_KEY_PEPPER`, `CREDENTIAL_KEK` all replaced, all distinct
- [ ] `CREDENTIAL_KEK` held in a KMS, not an environment variable
- [ ] `CORS_ORIGINS` set to real origins, never `*`
- [ ] TLS terminated in front of the service
- [ ] PostgreSQL reachable only from the application network
- [ ] `LOG_JSON=true`, and log shipping configured
- [ ] Database password rotated away from the compose default
- [ ] The application's database role does not own the tables, so RLS applies

See [production deployment](../deployment/production.md) for the rest.

## Related

- [Upstream credentials](credentials.md)
- [API keys](api-keys.md)
- [Threat model](threat-model.md)
