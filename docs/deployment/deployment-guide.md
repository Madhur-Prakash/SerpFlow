# Deployment guide

<p>
  <a href="../deployment/README.md"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="steps: 15" src="https://img.shields.io/badge/steps-15-2496ED">
  <img alt="TLS: Caddy" src="https://img.shields.io/badge/TLS-Caddy-1F88C0">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="nginx: 1.27" src="https://img.shields.io/badge/nginx-1.27-009639?logo=nginx&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Prometheus: metrics" src="https://img.shields.io/badge/Prometheus-metrics-E6522C?logo=prometheus&logoColor=white">
  <a href="../../backend/app/api/deps.py"><img alt="source: api/deps.py" src="https://img.shields.io/badge/source-api%2Fdeps.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 14 min" src="https://img.shields.io/badge/read-14%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../deployment/README.md) › **Deployment guide** · page 11 of 57

**A runbook: from a blank server to a verified production instance**, with every command. It deploys the bundled Docker Compose stack on **one host**, behind a TLS proxy.

- **Going multi-host?** Do this first, then read [production](production.md) for scaling, pooling and Kafka topology
- **Just trying it locally?** You want [installation](installation.md) instead
- **Hoping for a hosted instance instead?** There is none yet: SerpFlow is self-hosted by the author's decision, and will be hosted once enough people ask ([hosting](../../README.md#hosting))

**Steps:** [1 server](#1-prepare-the-server) · [2 code](#2-get-the-code) · [3 secrets](#3-generate-secrets) · [4 configure](#4-configure-the-environment) · [5 lock down ports](#5-lock-down-the-ports) · [6 known issue](#6-fix-the-docs-proxy-rule) · [7 build and start](#7-build-and-start) · [8 RLS backstop](#8-make-row-level-security-bind) · [9 TLS](#9-put-tls-in-front) · [10 first admin](#10-create-the-first-admin) · [11 verify](#11-verify-the-deployment) · [12 observability](#12-observability) · [13 backups](#13-backups) · [14 upgrades](#14-upgrades-and-rollback) · [15 cheat sheet](#15-operations-cheat-sheet)

## 1. Prepare the server

| Resource | Minimum | Comfortable |
| --- | --- | --- |
| CPU | 2 vCPU | 4 vCPU |
| Memory | 8 GB | 16 GB (Kafka's JVM and PostgreSQL are the big users) |
| Disk | 40 GB SSD | 100 GB+ (payloads, WAL, backups) |
| OS | Ubuntu 24.04 LTS, or any Linux with Docker | |

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git make curl ca-certificates ufw

# Docker Engine + Compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"      # log out and back in
docker compose version               # need 2.24+

# Firewall: SSH and web only
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

- **`ufw` does not filter ports Docker publishes.** Docker writes its own iptables rules. Step 5 handles that properly
- **Point DNS** for your domain (for example `serpflow.example.com`) at the server now, so TLS can issue in step 9

## 2. Get the code

```bash
git clone https://github.com/Madhur-Prakash/SerpFlow.git /opt/serpflow
cd /opt/serpflow
git checkout <release-tag>           # e.g. v1.0.0 (git tag lists them), or stay on main
```

- **The explicit target directory** keeps the path lowercase; a bare `git clone` creates `SerpFlow`
- What each release changed: [`CHANGELOG.md`](../../CHANGELOG.md)

## 3. Generate secrets

Every value distinct. Store them in a password manager or secret store **before** you continue. What each one protects: [secrets: inventory](../security/secrets.md#inventory); the same commands, with alternatives: [generating real ones](../security/secrets.md#generating-real-ones).

```bash
openssl rand -hex 32                 # JWT_SECRET
openssl rand -hex 32                 # API_KEY_PEPPER
openssl rand -base64 32              # CREDENTIAL_KEK  (32 random bytes, base64)
openssl rand -hex 24                 # POSTGRES_PASSWORD
openssl rand -hex 16                 # GRAFANA_PASSWORD
```

| Secret | If you lose it or change it carelessly |
| --- | --- |
| `CREDENTIAL_KEK` | every stored SerpApi/Groq credential becomes **undecryptable**. Rotate only with the [rewrap procedure](../security/secrets.md#kek); why it wraps per-credential keys: [ADR 0003](../adr/0003-envelope-encryption.md) |
| `API_KEY_PEPPER` | **every API key stops working**. Rotation means re-issuing all keys: [pepper rotation](../security/secrets.md#pepper) |
| `JWT_SECRET` | every user is signed out. Recoverable ([JWT secret rotation](../security/secrets.md#jwt-secret)) |
| `POSTGRES_PASSWORD` | only set at first initialisation of the volume; changing it later needs `ALTER ROLE` too |

## 4. Configure the environment

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Set at least these:

```bash
# --- environment
ENVIRONMENT=production
DEBUG=false

# --- secrets from step 3
JWT_SECRET=<hex>
API_KEY_PEPPER=<hex>
CREDENTIAL_KEK=<base64>
CREDENTIAL_KEK_ID=prod-kek-v1
POSTGRES_PASSWORD=<hex>
GRAFANA_PASSWORD=<hex>

# --- your public origin
FRONTEND_URL=https://serpflow.example.com
CORS_ORIGINS=https://serpflow.example.com
VITE_API_BASE_URL=https://serpflow.example.com

# --- startup bootstrap
RUN_MIGRATIONS_ON_STARTUP=true
SEED_ON_STARTUP=false

# --- behind your TLS proxy and the bundled nginx: two hops
TRUSTED_PROXY_HOPS=2

# --- logs and metrics
LOG_JSON=true
LOG_LEVEL=INFO
METRICS_ENABLED=true
```

Why the less obvious ones matter:

- **`VITE_API_BASE_URL` must be your public URL.** It is baked into the frontend bundle at build time ([Docker: the frontend image](docker.md#the-frontend-image))
  - left at the default, every visitor's browser calls **its own** `localhost:8000` ([troubleshooting](../operations/troubleshooting.md#the-production-frontend-calls-localhost8000))
  - an empty value does **not** work: compose's `${VITE_API_BASE_URL:-http://localhost:8000}` substitutes the default for empty as well as unset
- **`TRUSTED_PROXY_HOPS`** is how many proxies sit in front of the backend; the client IP is taken that far from the end of `X-Forwarded-For` ([`app/api/deps.py`](../../backend/app/api/deps.py))
  - TLS proxy + bundled nginx = **2**. At 1, the audit log, sessions and keys record the TLS proxy's address for every caller ([troubleshooting](../operations/troubleshooting.md#every-caller-is-recorded-with-the-proxys-ip))
  - the [rate limit](../api/overview.md#rate-limiting) is per principal and path, so this setting does not affect it
- **`SEED_ON_STARTUP`** is refused in `production` anyway: demo accounts with a published password never reach a real deployment ([the environment refusal](../operations/bootstrap.md#3-an-environment-refusal))
- **`POSTGRES_*` build the backend's `DATABASE_URL`:** compose overrides any `DATABASE_URL` in `.env` for the container ([Docker: how the backend container is configured](docker.md#running))
- **Do not set `SERPAPI_API_KEY`.** It does not exist. Organizations bring their own keys: [BYOK](../security/byok.md)
- **Leave `GROQ_API_KEY` unset** unless you intend your key to answer for every organization that has not brought one ([the self-hosting exception](../security/byok.md#the-self-hosting-exception))
- **`SERPFLOW_MODE`** is the instance default. `replay` is safe; projects opt into `live` themselves: [execution modes](../product/execution-modes.md)
- **Real email** (address verification, password reset, alert notifications): set `GMAIL_CREDENTIALS_B64` and `GMAIL_SENDER`, see [setting up Gmail](../operations/email.md#setting-up-gmail)
  - without it **nothing is delivered**: the log records only that a message would have been sent, never the link it carried
  - so **password resets need Gmail** in production ([troubleshooting](../operations/troubleshooting.md#password-reset-or-verification-email-never-arrives))
- **Object storage:** the default `filesystem` writes to the `object-data` volume. For S3, see [production: storage](production.md#storage)
- **The CLI, SDK and MCP variables** (`SERPFLOW_API_KEY`, `SERPFLOW_BASE_URL`, `SERPFLOW_MCP_SESSION`) do not belong in this file: those tools read them from the shell of whoever runs them ([local development: CLI, SDK and MCP](local.md#cli-sdk-and-mcp))

## 5. Lock down the ports

The bundled compose file publishes PostgreSQL, Redis and Kafka on **every interface**, which is right for a laptop and wrong for a server. Create `docker-compose.prod.yml`:

```yaml
# docker-compose.prod.yml - production overrides
services:
  postgres:
    ports: !reset []
  redis:
    ports: !reset []
  kafka:
    ports: !reset []
  backend:
    ports: !override
      - "127.0.0.1:8000:8000"
  frontend:
    ports: !override
      - "127.0.0.1:5173:80"
```

- **Datastores** become reachable only on the compose network ([troubleshooting: datastore ports are open](../operations/troubleshooting.md#datastore-ports-are-open-on-a-server))
- **The backend and frontend** listen on localhost only; the TLS proxy in step 9 is the one public entry point
- **Profile services publish ports too:** add `prometheus`, `grafana` and `minio` entries before starting a profile (step 12)
- `!reset` and `!override` need **Compose 2.24+**
- **Use both files on every command from here on:**

```bash
alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'
```

## 6. Fix the docs proxy rule

**A known issue in the bundled `frontend/nginx.conf`:** its API rule matches every path starting with `/docs`, so deep links into the in-app documentation return a JSON 404. Details: [Docker: known issue](docker.md#known-issue-docs-deep-links).

```bash
sed -i 's#location ~ ^/(v1|healthz|readyz|metrics|docs|redoc|openapi.json) {#location ~ ^/(v1|healthz|readyz|metrics|redoc|openapi\\.json)(/|$) {#' frontend/nginx.conf
grep -n "location ~ ^/(v1" frontend/nginx.conf      # confirm the new rule
```

- Swagger stays available on the API port (`127.0.0.1:8000/docs`), which is now private: reach it over an SSH tunnel
- The symptom this prevents: [troubleshooting: `/docs/...` returns a JSON 404](../operations/troubleshooting.md#docs-returns-a-json-404-in-the-container-deployment)

## 7. Build and start

```bash
dc build                              # backend and frontend images
dc up -d                              # postgres, redis, kafka, backend, frontend
dc ps                                 # wait for backend: (healthy)
dc logs -f backend                    # watch the bootstrap
```

Expect these events in the backend log:

```
bootstrap.migrations_start  ->  bootstrap.migrations_done  ->  app.startup
```

- **Migrations run under a PostgreSQL advisory lock:** start more replicas and they wait instead of racing. See [bootstrap](../operations/bootstrap.md#1-an-advisory-lock)
- **With `SEED_ON_STARTUP=false` there is no seed event**; left `true`, the log shows `bootstrap.seed_refused` and the server carries on ([the environment refusal](../operations/bootstrap.md#3-an-environment-refusal))
- **A migration failure is fatal:** the backend refuses to boot rather than serve an un-migrated schema, and `restart: unless-stopped` retries it ([failure behaviour](../operations/bootstrap.md#failure-behaviour))
- **Kafka topics** are auto-created on first use (the compose broker has auto-creation on, 3 partitions). To create all 8 up front, as `make kafka-topics` does ([topics](../operations/kafka.md#topics)):

```bash
dc exec backend python -m app.workers.topics
```

- **The API also runs the Kafka consumers in-process** while `KAFKA_ENABLED=true`, so this single-host stack needs no separate worker ([production: scaling](production.md#scaling))

## 8. Make row-level security bind

- **The table owner bypasses [row-level security](../database/rls.md) by default**, and the backend connects as the owner (`POSTGRES_USER`)
- **Worse, the official postgres image creates `POSTGRES_USER` as a superuser, and a superuser bypasses RLS always, `FORCE` included.** On the bundled compose stack, forcing alone changes nothing
  - **So first connect the backend as a separate role that is not a superuser**: the [`serpflow_app` recipe in production](production.md#before-anything-else). Until then the [application guards](../database/rls.md#the-application-guards) are the only tenant boundary
- Then force the policies onto the owner too, for any path that still connects as it. With the policy's [empty-setting clause](../database/rls.md#the-empty-value-clause), migrations and workers keep working. Why both RLS and application guards: [ADR 0006](../adr/0006-rls-plus-application-guards.md)

```bash
dc exec -T postgres psql -U serpflow -d serpflow <<'SQL'
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND rowsecurity LOOP
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;
SELECT count(*) AS forced FROM pg_class
WHERE relforcerowsecurity AND relnamespace = 'public'::regnamespace;
SQL
```

- **Expect `forced = 24`**: the 22 tenant tables of `0001_initial`, plus `organizations` and `custom_roles` ([covered tables](../database/rls.md#covered-tables))
- **A count is not proof.** Connected as the role the backend uses, run the `BEGIN ... ROLLBACK` check in [verifying it](../database/rls.md#verifying-it): it must return `0`. As a superuser it returns every row
- **Re-run it after any upgrade that adds a table**
- The separate application role, which this step depends on, is in [production](production.md#before-anything-else)

## 9. Put TLS in front

**Caddy** issues and renews certificates automatically:

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy
```

`/etc/caddy/Caddyfile`:

```
serpflow.example.com {
    encode gzip
    respond /metrics 404         # keep Prometheus metrics off the public origin
    reverse_proxy 127.0.0.1:5173 {
        flush_interval -1        # stream SSE frames immediately
    }
}
```

```bash
sudo systemctl reload caddy
curl -sI https://serpflow.example.com | head -1     # HTTP/2 200
curl -s -o /dev/null -w '%{http_code}\n' https://serpflow.example.com/metrics   # 404
```

- **One public origin** serves the app, the API (`/v1`, proxied by the bundled nginx) and the SSE stream
- **`/metrics` is unauthenticated**, and the bundled nginx proxies it ([`app/main.py`](../../backend/app/main.py), [`frontend/nginx.conf`](../../frontend/nginx.conf)). The `respond` line hides it publicly; Prometheus scrapes `backend:8000` on the compose network and is unaffected
- **`flush_interval -1`** matters: without it, pipeline frames arrive all at once at the end. See [streaming](../api/streaming.md#behind-a-proxy) and [troubleshooting](../operations/troubleshooting.md#the-stream-arrives-all-at-once-at-the-end)
- Using nginx instead? Copy the stream block from [production: behind a reverse proxy](production.md#behind-a-reverse-proxy)

## 10. Create the first admin

**No demo data exists in production**, so register the first owner. Registering creates the user **and** a new organization they own ([identity and access](../api/overview.md#identity-and-access)).

- **In the browser:** open `https://serpflow.example.com/register`
- **Or with curl** (the password needs 10 to 128 characters, mixing letters with digits or symbols: [`app/schemas/identity.py`](../../backend/app/schemas/identity.py)):

```bash
curl -s -X POST https://serpflow.example.com/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"<10+ chars, strong>","full_name":"Your Name","organization_name":"Your Org"}'
```

Then, signed in as the owner:

1. **Settings → Credentials:** add your **SerpApi** key, and optionally a **Groq** key ([adding a key](../security/byok.md#adding-a-key) · [how it is stored](../security/credentials.md#envelope-encryption))
2. **Settings → Projects:** create a project, and set its execution mode (`live` to spend real credits): [execution modes: setting it](../product/execution-modes.md#setting-it)
3. **Settings → API keys:** mint a `test` key for smoke tests and a `live` key for production use ([API keys](../security/api-keys.md))
4. **Budgets** (`/app/budgets`): set an organization budget before the first live call ([budget enforcement](../architecture/executor.md#budget-enforcement))
5. **Settings → Members:** add your team, and give each person the least role they need ([roles](../security/api-keys.md#roles))

## 11. Verify the deployment

```bash
curl -s https://serpflow.example.com/healthz          # {"status":"ok",...}
curl -s https://serpflow.example.com/readyz           # every check "ok"
dc exec backend python -m app.cli.main health        # the same, from inside
```

Smoke-test with the **test key**. It routes to the deterministic mock and **spends zero credits** ([test keys](../security/api-keys.md#test-keys) · [ADR 0005](../adr/0005-test-key-mode-precedence.md)):

```bash
export KEY=sf_test_...
curl -s -X POST https://serpflow.example.com/v1/plan \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"intent":"cafes in Koramangala","budget":5}' | head -c 400; echo
curl -s -D- -o /dev/null -X POST https://serpflow.example.com/v1/search \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"intent":"cafes in Koramangala","budget":5}' | grep -i x-serpflow-mode    # MOCK
```

| Check | Pass |
| --- | --- |
| `/readyz` | `"status":"ok"`, catalog `54` engines ([health](../operations/observability.md#health)) |
| `/v1/plan` with the test key | a plan with `naive_cost`, `marginal_cost`, `candidate_count` ([plan without executing](../api/overview.md#plan-without-executing)) |
| `/v1/search` with the test key | `X-SerpFlow-Mode: MOCK` ([provenance headers](../api/overview.md#provenance-headers)) |
| A docs deep link, e.g. `/docs/readme`, after a refresh | the docs page, not JSON (step 6) |
| The browser console on `/app/search` | no CORS errors (step 4) |
| `/metrics` on the public origin | `404` (step 9) |

- **`make demo` and `make api-check` are for staging**, not production: they expect the seeded demo organization
- **`dc exec backend python -m app.cli.main health`** is the `serpflow` CLI inside the container; from your own machine, the CLI reads `SERPFLOW_BASE_URL` from your shell ([CLI](../sdks/cli.md#serpflow-health))

## 12. Observability

**First keep both off the public internet.** Compose publishes them on every interface, and `ufw` will not stop it (step 1). Add to `docker-compose.prod.yml`:

```yaml
  prometheus:
    ports: !override
      - "127.0.0.1:9090:9090"
  grafana:
    ports: !override
      - "127.0.0.1:3001:3000"
```

- The same applies to `minio` (`9000`, `9001`) if you start the `storage` profile

```bash
dc --profile observability up -d                     # Prometheus + Grafana
ssh -L 3001:localhost:3001 -L 9090:localhost:9090 you@server   # view them privately
```

- **Grafana** at `http://localhost:3001` (user `GRAFANA_USER`, default `admin`, and `GRAFANA_PASSWORD`); Prometheus is provisioned as its datasource ([`docker/grafana/provisioning/`](../../docker/grafana/provisioning/datasources/prometheus.yml))
- **Prometheus scrapes `backend:8000/metrics` every 15 s** ([`docker/prometheus/prometheus.yml`](../../docker/prometheus/prometheus.yml)): 22 metrics, listed in [observability: metrics](../operations/observability.md#metrics)
- **Traces:** set `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` ([tracing](../operations/observability.md#tracing))
- **The alert that is specific to SerpFlow:** `serpflow_semantic_false_hit_reports_total` rising is a **correctness** page ([alerting](../operations/observability.md#alerting) · [the guard that should have caught each one](../architecture/caching.md#the-entity-and-numeral-guard))
- Rules and dashboards: [observability](../operations/observability.md)

## 13. Backups

**PostgreSQL** is the source of truth:

```bash
mkdir -p /opt/backups
dc exec -T postgres pg_dump -U serpflow -Fc serpflow > /opt/backups/serpflow-$(date +%F).dump
```

**Object payloads** (filesystem storage):

```bash
docker run --rm -v serpflow_object-data:/data -v /opt/backups:/b alpine \
  tar czf /b/objects-$(date +%F).tgz -C /data .
```

**Nightly**, with `crontab -e`:

```
15 3 * * * cd /opt/serpflow && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres pg_dump -U serpflow -Fc serpflow > /opt/backups/serpflow-$(date +\%F).dump
```

**Restore**, then prove nothing was lost:

```bash
dc exec -T postgres pg_restore -U serpflow -d serpflow --clean --if-exists < /opt/backups/serpflow-YYYY-MM-DD.dump
curl -s -H "Authorization: Bearer <owner token>" https://serpflow.example.com/v1/audit/verify
```

- **`/v1/audit/verify` walks the audit log's hash chain** and reports the first break, so a restore that lost entries shows up. It needs `audit:read` (owner or admin): [the audit log](../database/rls.md#the-audit-log)
- **Redis needs no backup:** it is a hot cache and repopulates lazily ([why none of it is authoritative](../operations/redis.md#why-none-of-it-is-authoritative))
- **The volume names** carry the compose project prefix, `serpflow_` ([Docker: volumes](docker.md#volumes))
- **Copy backups off the server**, and test a restore before you need one. Point-in-time recovery: [production: PostgreSQL](production.md#postgresql)

## 14. Upgrades and rollback

```bash
cd /opt/serpflow
dc exec -T postgres pg_dump -U serpflow -Fc serpflow > /opt/backups/pre-upgrade-$(date +%F).dump
git fetch --tags && git checkout <new-release-tag>
dc build
dc up -d                               # migrations apply on start, advisory-locked
dc logs --tail=100 backend             # bootstrap.migrations_done, app.startup
```

- **Re-apply step 6** if `frontend/nginx.conf` changed upstream, and **step 8** if the release added tables ([the revision chain](../database/migrations.md#the-revision-chain))
- **Migrations are expand-only**, so the previous release still runs against the upgraded schema ([zero-downtime deploys](production.md#zero-downtime-deploys))

**Rollback:**

```bash
git checkout <previous-release-tag>
dc build && dc up -d
```

- **Only if a migration must be undone:** `dc exec backend python -m alembic downgrade -1`. Read its `downgrade()` first, or restore the pre-upgrade dump instead ([migrations: commands](../database/migrations.md#commands))

## 15. Operations cheat sheet

| Task | Command |
| --- | --- |
| Status | `dc ps` |
| Logs | `dc logs -f --tail=200 backend` |
| Restart one service | `dc restart backend` |
| SQL shell | `dc exec postgres psql -U serpflow -d serpflow` |
| Redis shell | `dc exec redis redis-cli` |
| Health | `dc exec backend python -m app.cli.main health` |
| Kafka topics | `dc exec backend python -m app.workers.topics` |
| Stop, keep data | `dc down` |
| Stop and **delete all data** | `dc down -v` |

**Rotations:** [secrets](../security/secrets.md#rotation) · [API keys](../security/api-keys.md) · [upstream credentials](../security/credentials.md)

## Pre-launch checklist

| | Item | Step |
| --- | --- | --- |
| 1 | `ENVIRONMENT=production`, `DEBUG=false` | 4 |
| 2 | `JWT_SECRET`, `API_KEY_PEPPER`, `CREDENTIAL_KEK` generated, distinct, stored safely | 3 |
| 3 | `VITE_API_BASE_URL`, `CORS_ORIGINS`, `FRONTEND_URL` set to the public origin | 4 |
| 4 | `TRUSTED_PROXY_HOPS=2` behind TLS + nginx | 4 |
| 5 | Datastore ports unpublished; app bound to localhost | 5 |
| 6 | `/docs` proxy rule fixed | 6 |
| 7 | Backend connects as a non-superuser; `FORCE ROW LEVEL SECURITY` on all 24 tables; the RLS check returns `0` | 8 |
| 8 | TLS working; SSE streams frame by frame | 9 |
| 9 | Organization budget set before the first live call | 10 |
| 10 | Test-key smoke test passes; `X-SerpFlow-Mode: MOCK` | 11 |
| 11 | Nightly backups, copied off-host, restore tested | 13 |
| 12 | `/metrics` returns 404 on the public origin; Prometheus and Grafana bound to `127.0.0.1` | 9, 12 |

- The same list from the security side: [secrets: production checklist](../security/secrets.md#production-checklist)

## Related

- [Installation](installation.md): the laptop version of this, with no secrets to generate
- [Docker](docker.md): the compose file, images and healthchecks this runbook deploys
- [Production](production.md): scaling, pooling, Kafka topology, zero-downtime deploys
- [Secrets](../security/secrets.md): what each secret protects, and how to rotate it
- [Startup bootstrap](../operations/bootstrap.md): what happens in step 7, and why seeding is refused here
- [Row-level security](../database/rls.md): the policies step 8 forces onto the owner
- [Threat model](../security/threat-model.md): what the locked ports, TLS and RLS steps defend against
- [Troubleshooting: deployment](../operations/troubleshooting.md#deployment): the failures this runbook's steps prevent

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Docker](../deployment/docker.md) | [Docs index](../README.md) · [Deployment index](../deployment/README.md) | [Production](../deployment/production.md) |
