# Secrets

<p>
  <a href="../security/README.md"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="JWT: HS256" src="https://img.shields.io/badge/JWT-HS256-000000?logo=jsonwebtokens&logoColor=white">
  <img alt="AES: 256-GCM" src="https://img.shields.io/badge/AES-256--GCM-6E40C9">
  <a href="../../backend/app/core/config.py"><img alt="source: core/config.py" src="https://img.shields.io/badge/source-core%2Fconfig.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 12 min" src="https://img.shields.io/badge/read-12%20min-555555">
</p>

[Docs](../README.md) › [Security](../security/README.md) › **Secrets** · page 43 of 57

**Every secret the service holds, where it lives, and what happens if it leaks.**

- Configuration is entirely environment-driven: the API reads the environment first, then `.env` in its working directory, then `../.env`
- The authoritative list: [`.env.example`](../../.env.example) · the types: [`app/core/config.py`](../../backend/app/core/config.py)
- **This page covers every variable in both**: the secrets below, the [shell-only client variables](#cli-sdk-and-mcp-read-from-the-shell), and [everything else](#everything-else-in-envexample), which is configuration rather than secret

## Inventory

| Secret | Variable | Protects | If it leaks | Used by |
| --- | --- | --- | --- | --- |
| KEK | `CREDENTIAL_KEK` | every upstream credential in the vault, SerpApi and Groq | rewrap every DEK under a new KEK ([KEK](#kek)) | [credentials](credentials.md#envelope-encryption) |
| API key pepper | `API_KEY_PEPPER` | API key hashes; also refresh-session, email-verification, password-reset and webhook-secret hashes | every key must be reissued, every user logs in again ([pepper](#pepper)) | [API keys](api-keys.md#hashing-hmac-sha256-not-argon2) |
| JWT secret | `JWT_SECRET` | browser sessions: access and refresh tokens are both JWTs | sessions are forgeable; rotate, all users re-login ([JWT secret](#jwt-secret)) | [API: authentication](../api/overview.md#authentication) |
| Database password | `POSTGRES_PASSWORD`, and inside `DATABASE_URL` | everything at rest | rotate and re-check network exposure | [deployment guide](../deployment/deployment-guide.md#3-generate-secrets) |
| Object storage keys | `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (also MinIO's root user and password in compose) | stored SERP payloads | rotate; payloads are content-addressed, not secret by themselves | [caching: object storage](../architecture/caching.md#object-storage) |
| Webhook secrets | per channel, stored as an HMAC under the pepper | delivery authenticity | per-channel rotation only | [`notification_channels`](../database/schema.md#notification_channels) |
| Gmail credential | `GMAIL_CREDENTIALS_B64` | sending mail as your sender (`gmail.send` scope only) | revoke the OAuth grant in Google, mint a new one | [email](../operations/email.md#setting-up-gmail) |
| Groq key, self-hosting only | `GROQ_API_KEY` | the planner's model, for organizations that brought none | upstream billing only; no SerpFlow data at risk | [BYOK: self-hosting exception](byok.md#the-self-hosting-exception) |
| Grafana admin | `GRAFANA_USER`, `GRAFANA_PASSWORD` (`admin` / `admin` by default) | dashboards and their Prometheus data source | change it; Grafana sees metrics, not tenant data | [observability: dashboards](../operations/observability.md#dashboards) |
| SerpApi key | none: encrypted in the vault, per organization | upstream spend | see [credentials](credentials.md) | [bring your own key](byok.md) |

- **Blast radii are deliberately different sizes**
  - a leaked JWT secret costs every user a re-login
  - a leaked pepper costs every API key, and every refresh session with it
- **That is why they are separate values**, not one `SECRET_KEY` reused everywhere
  - the common shortcut, and the reason one leak usually means total compromise
- **A webhook channel's stored hash is also its signing key:** deliveries carry `x-serpflow-signature`, an HMAC-SHA256 of the body keyed by `secret_hash` itself, not by the secret the channel was created with ([`handle_webhook`](../../backend/app/workers/consumers/handlers.py))

### CLI, SDK and MCP: read from the shell

**Client-side variables.** The `serpflow` CLI, the Python SDK and `serpflow-mcp` read these from the **shell**; the API never reads them, and nothing loads `.env` into your shell for you. They appear, commented out, in the "CLI, SDK and MCP" block of [`.env.example`](../../.env.example) so every variable lives in one place: `export` them instead of uncommenting.

| Variable | Read by | Ignored by | What it does |
| --- | --- | --- | --- |
| `SERPFLOW_API_KEY` | CLI (fallback for `--api-key`), Python SDK (fallback for `api_key=`), MCP server (**required**) | the API, the TypeScript SDK | the key every call runs under. A secret: handle it like any [API key](api-keys.md) |
| `SERPFLOW_BASE_URL` | CLI (fallback for `--base-url`), Python SDK (read once, at import) | the API, the TypeScript SDK, the MCP server | the API's URL, `http://localhost:8000` by default |
| `SERPFLOW_MCP_SESSION` | MCP server only | everything else | names the [service session](api-keys.md#service-principal-sessions); the same name resumes it, so the session cap is checked before each call and holds across restarts. Unset, each tool call opens a fresh session and the cap is never checked |

- Code: [`app/cli/main.py`](../../backend/app/cli/main.py), [`app/sdk/__init__.py`](../../backend/app/sdk/__init__.py), [`app/mcp/server.py`](../../backend/app/mcp/server.py)
- **The TypeScript SDK reads no environment at all:** pass `apiKey` and `baseUrl` ([TypeScript SDK: configure](../sdks/typescript.md#configure))
- **The MCP server runs the services in-process**, so it ignores `SERPFLOW_BASE_URL` and instead needs the API's own `DATABASE_URL`, `API_KEY_PEPPER` and, for live runs, `CREDENTIAL_KEK` ([MCP: configuration](../sdks/mcp.md#configuration))
- More: [SDKs: configuration](../sdks/overview.md#configuration), [CLI](../sdks/cli.md), [Python SDK: configure](../sdks/python.md#configure)

### Everything else in `.env.example`

**Configuration, not secrets.** Listed so the inventory is complete; each is documented where it is used.

| Area | Variables | Documented in |
| --- | --- | --- |
| Service | `SERVICE_NAME` (also the JWT issuer), `ENVIRONMENT`, `DEBUG`, `API_V1_PREFIX` | [production](../deployment/production.md#before-anything-else), [bootstrap: an environment refusal](../operations/bootstrap.md#3-an-environment-refusal) |
| Execution | `SERPFLOW_MODE`: the instance default mode, `live`, `record` or `replay` (`replay` if unset); a project's own mode, a per-request override and a `test` key all take precedence. `CASSETTE_DIR`: where `record` writes cassettes and `replay` reads them | [execution modes](../product/execution-modes.md#who-chooses-and-precedence) |
| PostgreSQL | `DATABASE_URL`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_ECHO`; compose only: `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PORT` | [production: PostgreSQL](../deployment/production.md#postgresql), [Docker: PostgreSQL](../deployment/docker.md#postgresql) |
| Redis | `REDIS_URL`, `REDIS_PRINCIPAL_CACHE_TTL`; compose only: `REDIS_PORT` | [Redis: configuration](../operations/redis.md#configuration) |
| Kafka | `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_CLIENT_ID`, `KAFKA_CONSUMER_GROUP`, `KAFKA_ENABLED`; compose only: `KAFKA_PORT`, `KAFKA_CLUSTER_ID` | [Kafka](../operations/kafka.md), [Docker: Kafka](../deployment/docker.md#kafka) |
| Object storage | `STORAGE_BACKEND`, `STORAGE_LOCAL_PATH`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`; compose only: `MINIO_PORT`, `MINIO_CONSOLE_PORT` | [caching: object storage](../architecture/caching.md#object-storage) |
| Tokens and requests | `JWT_ALGORITHM`, `ACCESS_TOKEN_TTL_SECONDS`, `REFRESH_TOKEN_TTL_SECONDS`, `CREDENTIAL_KEK_ID`, `CORS_ORIGINS`, `RATE_LIMIT_PER_MINUTE`, `MAX_REQUEST_BODY_BYTES`, `TRUSTED_PROXY_HOPS` | [API: rate limiting](../api/overview.md#rate-limiting), [threat model: denial of service](threat-model.md#denial-of-service), [production: behind a reverse proxy](../deployment/production.md#behind-a-reverse-proxy) |
| Startup | `RUN_MIGRATIONS_ON_STARTUP`, `SEED_ON_STARTUP` | [bootstrap](../operations/bootstrap.md) |
| Email | `FRONTEND_URL`, `GMAIL_SENDER`, `EMAIL_FROM_NAME`, `EMAIL_VERIFICATION_TTL_SECONDS`, `PASSWORD_RESET_TTL_SECONDS` | [email](../operations/email.md) |
| Upstream transport | `SERPAPI_BASE_URL`, `SERPAPI_TIMEOUT_SECONDS`, `LLM_PROVIDER`, `GROQ_BASE_URL`, `GROQ_MODEL`, `GROQ_TIMEOUT_SECONDS` | [bring your own key](byok.md#the-self-hosting-exception), [planner: which adapter plans](../architecture/planner.md#which-adapter-plans) |
| Planner and cache | `EMBEDDING_DIM`, `PLANNER_RETRIEVAL_TOP_K`, `PLANNER_MAX_CANDIDATES`, `PLANNER_MAX_HOPS`, `SEMANTIC_SIMILARITY_THRESHOLD`, `CACHE_PARTITION_SCOPE`, `ADAPTIVE_TTL_MIN_SECONDS`, `ADAPTIVE_TTL_MAX_SECONDS`, `DEFAULT_BUDGET_ALERT_RATIO` | [planner](../architecture/planner.md), [caching](../architecture/caching.md) |
| Retention | `RETENTION_STANDARD_DAYS`, `RETENTION_HIGH_PII_DAYS` | [executor: retention](../architecture/executor.md#retention) |
| Observability | `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `LOG_LEVEL`, `LOG_JSON`, `LOG_FILE`, `LOG_OUTPUT`, `METRICS_ENABLED`; compose only: `PROMETHEUS_PORT`, `GRAFANA_PORT` | [observability](../operations/observability.md) |
| Ports and frontend build | compose only: `BACKEND_PORT`, `FRONTEND_PORT`, `VITE_API_BASE_URL` (baked into the frontend bundle at build time) | [Docker: service configuration](../deployment/docker.md#service-configuration), [Docker: the frontend image](../deployment/docker.md#the-frontend-image) |

- **"Compose only" variables are read by [`docker-compose.yml`](../../docker-compose.yml), not by `Settings`**
- **There is no `SERPAPI_API_KEY`.** Searches spend the organization's own key ([bring your own key](byok.md#the-self-hosting-exception))

## Where they are not

- **Not in the database.** The pepper and the KEK are process environment only. A database dump cannot verify a guessed API key or decrypt a credential ([threat model: credential theft from the database](threat-model.md#credential-theft-from-the-database))
- **Not in the repository.** `.env` and `.env.*` are gitignored, except `.env.example`, which holds only obvious placeholders; the deployment secrets in it are marked `CHANGE ME`
- **Not in a log.** `CredentialRedactionFilter` is installed on the root logger, and scrubs message, args, `extra=` attributes and the exception path ([credentials: never in a log](credentials.md#never-in-a-log))
- **Not in an error response.** Errors carry a stable code, a sentence and a request id. Never a stack trace, never a configuration value ([API: errors](../api/overview.md#errors))
- **Not in a response schema.** No field anywhere in `app/schemas` could carry a credential, and a test asserts it by walking every response model

## Local development

- **The defaults in `.env.example` are deliberately working values**, because `make dev` and `make seed` must work with **no keys at all** ([local development](../deployment/local.md#first-run))
  - the local KEK is a published base64 string
  - the pepper and JWT secret both start `change-me-`: `change-me-api-key-pepper-local-dev-only` and `change-me-in-production-this-is-a-local-dev-default`
  - [`app/core/config.py`](../../backend/app/core/config.py) carries the same three values as defaults, so an unset variable still boots
- **This is a trade:**
  - a setup that demands four secrets before it boots gets them generated badly, or shared
  - a setup that boots with obvious placeholders makes the danger **visible**: `change-me-in-production` in a production environment is grep-able, alarming and easy to catch in review
- **With no keys at all you get:**
  - deterministic planning, no network, until an organization brings a Groq key
  - `SERPFLOW_MODE=replay`: cassettes only, never the network ([execution modes](../product/execution-modes.md#the-four-modes))
  - `sf_test_...` keys: deterministic mock results, zero SerpApi credits ([API keys: test keys](api-keys.md#test-keys))
- **The upstream keys are not in this file.** SerpApi and Groq access is [bring-your-own-key](byok.md): each organization's keys live encrypted in the credential vault. The secrets above belong to the deployment itself

## Generating real ones

```bash
# 32-byte KEK, base64
openssl rand -base64 32
# or: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"

# pepper and JWT secret
openssl rand -hex 32
# or: python -c "import secrets; print(secrets.token_urlsafe(48))"
```

- **Each value distinct**
- **From a secret manager, not a file**, in any environment that is not a laptop
- Where they go in a real deployment: [deployment guide, steps 3-4](../deployment/deployment-guide.md#3-generate-secrets)

## Rotation

### KEK

**Envelope encryption is what makes this cheap:** only the wrapped DEKs change; the ciphertext does not move ([ADR 0003](../adr/0003-envelope-encryption.md)).

- **The process holds one KEK at a time.** `kek_id` is written on every row, but `_load_kek` reads only `CREDENTIAL_KEK`, and `decrypt_credential` does not consult `kek_id` ([`app/core/security.py`](../../backend/app/core/security.py)). So a rotation is an offline re-wrap, and no tool for it ships yet:

1. Stop the API, the workers and the MCP server, or accept that runs fail until step 3
2. With a one-off script holding both keys: for each credential, unwrap the DEK with the old KEK, rewrap it with the new, update `encrypted_dek` and `kek_id`
3. Set `CREDENTIAL_KEK` and `CREDENTIAL_KEK_ID` to the new values everywhere, and restart

- **Cost is proportional to the number of credentials**, not to the volume of encrypted data
- **A KEK changed without the re-wrap** leaves every credential undecryptable: live runs fail, and an organization's Groq key falls back to deterministic planning

### Pepper

- **The pepper is an input to the hash**, so rotating it invalidates **every** stored hash
- There is no re-peppering without the plaintext, and the plaintext is gone **by design**
- **It is one value at a time.** `hash_api_key` reads only `API_KEY_PEPPER`, so there is no window in which keys hashed under the old and the new pepper both verify, and the [rotation grace window](api-keys.md#rotation) cannot bridge it
- **Switching it breaks, at once:**
  - every API key (`INVALID_API_KEY`)
  - every refresh session, so every user logs in again
  - outstanding email-verification and password-reset links
  - webhook channels keep signing with their stored hash, so they are unaffected
- **The procedure is a flag day:**

1. Switch the pepper on the API, the workers and the MCP server together
2. Reissue every API key and hand out the new ones
3. Expect every user to log in again

- **Plan for this before you need it.** It is the most disruptive rotation in the system: the correct trade for a value that never has to be read back

### JWT secret

- **Sessions signed with the old secret stop verifying**, so every user is logged out
- Access tokens live **15 minutes**, refresh tokens **14 days** (`ACCESS_TOKEN_TTL_SECONDS`, `REFRESH_TOKEN_TTL_SECONDS`); both are JWTs, so rotating the secret cuts both immediately
- **There is no dual-secret window:** [`decode_token`](../../backend/app/core/security.py) verifies against `JWT_SECRET` alone. A planned rotation still logs everyone out; schedule it
- **`SERVICE_NAME` is the token issuer** (`iss`), checked on decode, so changing it has the same effect

## Production checklist

| Check | Done when |
| --- | --- |
| Environment | `ENVIRONMENT=production` and `DEBUG=false`; this also refuses `SEED_ON_STARTUP` ([bootstrap](../operations/bootstrap.md#3-an-environment-refusal)) |
| Deployment secrets | `JWT_SECRET`, `API_KEY_PEPPER`, `CREDENTIAL_KEK` all replaced, all distinct, and `CREDENTIAL_KEK_ID` renamed to match |
| KEK custody | `CREDENTIAL_KEK` injected from a secret manager or KMS at deploy time, never committed; on a single host, at least a `chmod 600` `.env` ([production](../deployment/production.md#before-anything-else)). The code reads it from the environment; keeping it out of the environment entirely needs `_load_kek` replaced with a KMS call |
| CORS | `CORS_ORIGINS` set to real origins, never `*` |
| Transport | TLS terminated in front of the service, by a proxy that appends to `X-Forwarded-For`, and `TRUSTED_PROXY_HOPS` matching the number of such proxies. Without one, recorded client addresses can be spoofed ([threat model: exposed surfaces](threat-model.md#exposed-surfaces)) |
| Metrics | `/metrics` not reachable from the public origin: it is unauthenticated and its labels name organizations and projects ([deployment guide, step 9](../deployment/deployment-guide.md#9-put-tls-in-front)) |
| Network | PostgreSQL reachable only from the application network |
| Logs | `LOG_JSON=true`, and log shipping configured |
| Database | password rotated away from the compose default |
| Side services | `GRAFANA_PASSWORD` and the MinIO / S3 keys changed from `admin` / `serpflow-secret` |
| RLS | the application's database role is neither a superuser nor the tables' owner, or owns them with `FORCE ROW LEVEL SECURITY` set ([row-level security](../database/rls.md#verifying-it)) |

- The full runbook: [deployment guide](../deployment/deployment-guide.md#pre-launch-checklist) · the rest: [production](../deployment/production.md)

## Related

- [Upstream credentials](credentials.md): what the KEK protects, and how a credential is decrypted
- [API keys](api-keys.md): what the pepper protects, and how keys rotate
- [Bring your own key](byok.md): why the upstream keys are not in this inventory
- [Threat model](threat-model.md#out-of-scope): a compromised host holds the KEK and the pepper
- [Deployment guide: generate secrets](../deployment/deployment-guide.md#3-generate-secrets): where these values go on a real server
- [SDKs: configuration](../sdks/overview.md#configuration): the shell variables each client reads
- [Troubleshooting: `INVALID_API_KEY` on a key that looks right](../operations/troubleshooting.md#invalid_api_key-on-a-key-that-looks-right): a changed pepper looks exactly like this
- [Installation](../deployment/installation.md): where the secrets are first generated

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [API keys](../security/api-keys.md) | [Docs index](../README.md) · [Security index](../security/README.md) | [Operations index](../operations/README.md) |
