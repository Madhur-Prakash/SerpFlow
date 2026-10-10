# Deployment guide

<p>
  <a href="../README.md#deployment"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="steps: 15" src="https://img.shields.io/badge/steps-15-2496ED">
  <img alt="TLS: Caddy" src="https://img.shields.io/badge/TLS-Caddy-1F88C0">
  <img alt="Docker: Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="nginx: 1.27" src="https://img.shields.io/badge/nginx-1.27-009639?logo=nginx&logoColor=white">
  <img alt="PostgreSQL: 17 + pgvector" src="https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Prometheus: metrics" src="https://img.shields.io/badge/Prometheus-metrics-E6522C?logo=prometheus&logoColor=white">
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../README.md#deployment) › **Deployment guide** · page 8 of 50

**A runbook: from a blank server to a verified production instance**, with every command. It deploys the bundled Docker Compose stack on **one host**, behind a TLS proxy.

- **Going multi-host?** Do this first, then read [production](production.md) for scaling, pooling and Kafka topology
- **Just trying it locally?** You want [installation](installation.md) instead

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
git clone https://github.com/serpflow/serpflow.git /opt/serpflow
cd /opt/serpflow
git checkout <release-tag>           # or stay on main
```

## 3. Generate secrets

Every value distinct. Store them in a password manager or secret store **before** you continue.

```bash
openssl rand -hex 32                 # JWT_SECRET
openssl rand -hex 32                 # API_KEY_PEPPER
openssl rand -base64 32              # CREDENTIAL_KEK  (32 random bytes, base64)
openssl rand -hex 24                 # POSTGRES_PASSWORD
openssl rand -hex 16                 # GRAFANA_PASSWORD
```

| Secret | If you lose it or change it carelessly |
| --- | --- |
| `CREDENTIAL_KEK` | every stored SerpApi/Groq credential becomes **undecryptable**. Rotate only with the [rewrap procedure](../security/secrets.md#kek) |
| `API_KEY_PEPPER` | **every API key stops working**. Rotation means re-issuing all keys: [pepper rotation](../security/secrets.md#pepper) |
| `JWT_SECRET` | every user is signed out. Recoverable |
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

- **`VITE_API_BASE_URL` must be your public URL.** It is baked into the frontend bundle at build time
  - left at the default, every visitor's browser calls **its own** `localhost:8000`
  - an empty value does **not** work: compose's `${VITE_API_BASE_URL:-http://localhost:8000}` substitutes the default for empty as well as unset
- **`TRUSTED_PROXY_HOPS`** is how many proxies sit in front of the backend; the client IP is taken that far from the end of `X-Forwarded-For`
  - TLS proxy + bundled nginx = **2**. At 1, every visitor shares one rate-limit bucket
- **`SEED_ON_STARTUP`** is refused in `production` anyway: demo accounts with a published password never reach a real deployment
- **Do not set `SERPAPI_API_KEY`.** It does not exist. Organizations bring their own keys: [BYOK](../security/byok.md)
- **Leave `GROQ_API_KEY` unset** unless you intend your key to answer for every organization that has not brought one
- **`SERPFLOW_MODE`** is the instance default. `replay` is safe; projects opt into `live` themselves: [execution modes](../product/execution-modes.md)
- **Real email** (address verification, password reset, alert notifications): set `GMAIL_CREDENTIALS_B64` and `GMAIL_SENDER`, see [email](../operations/email.md)
  - without it **nothing is delivered**: the log records only that a message would have been sent, never the link it carried
  - so **password resets need Gmail** in production
- **Object storage:** the default `filesystem` writes to the `object-data` volume. For S3, see [production: storage](production.md#storage)

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

- **Datastores** become reachable only on the compose network
- **The backend and frontend** listen on localhost only; the TLS proxy in step 9 is the one public entry point
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

- **Migrations run under a PostgreSQL advisory lock:** start more replicas and they wait instead of racing. See [bootstrap](../operations/bootstrap.md)
- **Kafka topics** are auto-created on first use. To create them explicitly with intentional partition counts:

```bash
dc exec backend python -m app.workers.topics
```

## 8. Make row-level security bind

- **The table owner bypasses row-level security by default**, and the backend connects as the owner (`POSTGRES_USER`)
- Force the policies onto the owner too. With the policy's empty-setting clause, migrations and workers keep working:

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

- **Expect `forced = 24`**
- **Re-run it after any upgrade that adds a table**
- The alternative, a separate non-owner application role, is in [production](production.md#before-anything-else)

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
    reverse_proxy 127.0.0.1:5173 {
        flush_interval -1        # stream SSE frames immediately
    }
}
```

```bash
sudo systemctl reload caddy
curl -sI https://serpflow.example.com | head -1     # HTTP/2 200
```

- **One public origin** serves the app, the API (`/v1`, proxied by the bundled nginx) and the SSE stream
- **`flush_interval -1`** matters: without it, pipeline frames arrive all at once at the end. See [streaming](../api/streaming.md#behind-a-proxy)
- Using nginx instead? Copy the stream block from [production: behind a reverse proxy](production.md#behind-a-reverse-proxy)

## 10. Create the first admin

**No demo data exists in production**, so register the first owner. Registering creates the user **and** a new organization they own.

- **In the browser:** open `https://serpflow.example.com/register`
- **Or with curl:**

```bash
curl -s -X POST https://serpflow.example.com/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"<10+ chars, strong>","full_name":"Your Name","organization_name":"Your Org"}'
```

Then, signed in as the owner:

1. **Settings → Credentials:** add your **SerpApi** key, and optionally a **Groq** key
2. **Settings → Projects:** create a project, and set its execution mode (`live` to spend real credits)
3. **Settings → API keys:** mint a `test` key for smoke tests and a `live` key for production use
4. **Budgets:** set an organization budget before the first live call
5. **Settings → Members:** add your team, and give each person the least role they need ([roles](../security/api-keys.md#roles))

## 11. Verify the deployment

```bash
curl -s https://serpflow.example.com/healthz          # {"status":"ok",...}
curl -s https://serpflow.example.com/readyz           # every check "ok"
dc exec backend python -m app.cli.main health        # the same, from inside
```

Smoke-test with the **test key**. It routes to the deterministic mock and **spends zero credits**:

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
| `/readyz` | `"status":"ok"`, catalog `54` engines |
| `/v1/plan` with the test key | a plan with `naive_cost`, `marginal_cost`, `candidate_count` |
| `/v1/search` with the test key | `X-SerpFlow-Mode: MOCK` |
| A docs deep link, e.g. `/docs/readme`, after a refresh | the docs page, not JSON (step 6) |
| The browser console on `/app/search` | no CORS errors (step 4) |

- **`make demo` and `make api-check` are for staging**, not production: they expect the seeded demo organization

## 12. Observability

```bash
dc --profile observability up -d                     # Prometheus + Grafana
ssh -L 3001:localhost:3001 -L 9090:localhost:9090 you@server   # view them privately
```

- **Grafana** at `http://localhost:3001` (user `admin`, `GRAFANA_PASSWORD`); Prometheus is provisioned as its datasource
- **Keep both off the public internet:** bind them to `127.0.0.1` in `docker-compose.prod.yml`, as in step 5
- **Traces:** set `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT`
- **The alert that is specific to SerpFlow:** `serpflow_semantic_false_hit_reports_total` rising is a **correctness** page
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

- **Redis needs no backup:** it is a hot cache and repopulates lazily
- **Copy backups off the server**, and test a restore before you need one

## 14. Upgrades and rollback

```bash
cd /opt/serpflow
dc exec -T postgres pg_dump -U serpflow -Fc serpflow > /opt/backups/pre-upgrade-$(date +%F).dump
git fetch --tags && git checkout <new-release-tag>
dc build
dc up -d                               # migrations apply on start, advisory-locked
dc logs --tail=100 backend             # bootstrap.migrations_done, app.startup
```

- **Re-apply step 6** if `frontend/nginx.conf` changed upstream, and **step 8** if the release added tables
- **Migrations are expand-only**, so the previous release still runs against the upgraded schema

**Rollback:**

```bash
git checkout <previous-release-tag>
dc build && dc up -d
```

- **Only if a migration must be undone:** `dc exec backend python -m alembic downgrade -1`. Read its `downgrade()` first, or restore the pre-upgrade dump instead

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
| 7 | `FORCE ROW LEVEL SECURITY` on all 24 tables | 8 |
| 8 | TLS working; SSE streams frame by frame | 9 |
| 9 | Organization budget set before the first live call | 10 |
| 10 | Test-key smoke test passes; `X-SerpFlow-Mode: MOCK` | 11 |
| 11 | Nightly backups, copied off-host, restore tested | 13 |

## Related

- [Installation](installation.md)
- [Docker](docker.md)
- [Production](production.md): scaling, pooling, Kafka topology, zero-downtime deploys
- [Secrets](../security/secrets.md)
- [Troubleshooting](../operations/troubleshooting.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Docker](../deployment/docker.md) | [Docs index](../README.md) | [Production](../deployment/production.md) |
