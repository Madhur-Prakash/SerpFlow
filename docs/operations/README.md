# Operations

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="pages: 6" src="https://img.shields.io/badge/pages-6-E6522C">
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Operations** · page 44 of 50

**Running a SerpFlow instance: how it boots, what it sends, how to watch it, how it degrades when Kafka or Redis is down, and what to do when something fails.**

- **Read it to** boot an instance from an empty database, wire up email, metrics and traces, run the workers, and fix the failures you will actually hit
- **For whoever runs the instance**, on a laptop or a server. Each service page says what happens when its dependency is missing or down
- **Something broken now? Go straight to [troubleshooting](troubleshooting.md)**, which starts from `make health` and `/readyz`
- **New here? Start with [bootstrap: what happens](bootstrap.md#what-happens)**: everything between the container starting and the server serving

## Pages

| # | Page | Read it to |
| --- | --- | --- |
| 1 | [Startup bootstrap](bootstrap.md) | see how two variables turn a container and an empty database into a working instance, safely across replicas |
| 2 | [Email](email.md) | send verification, password-reset and notification email through Gmail, and know what is sent without it |
| 3 | [Observability](observability.md) | read the structured logs, 22 metrics and traces, and choose what to alert on |
| 4 | [Kafka](kafka.md) | learn what goes through the broker and what never does, and run the consumers |
| 5 | [Redis](redis.md) | see what Redis holds, why losing it costs latency and not credits, and how to size it |
| 6 | [Troubleshooting](troubleshooting.md) | match a symptom or an error code to its cause and its fix |

## Questions this section answers

| If you want to know | Go to |
| --- | --- |
| Is it safe to leave the bootstrap on when several replicas start at once? | [Bootstrap: an advisory lock](bootstrap.md#1-an-advisory-lock) |
| How do I make email actually send, instead of going to the log? | [Email: setting up Gmail](email.md#setting-up-gmail) |
| Which metric shows marginal-cost replanning changing a plan? | [Observability: the thesis metric](observability.md#the-thesis-metric) |
| How do I follow one failed request from its response to the logs and the trace? | [Observability: correlating one request](observability.md#correlating-one-request) |
| Does an interactive search go through Kafka? | [Kafka: what goes through it, and what does not](kafka.md#what-goes-through-it-and-what-does-not) |
| What do I lose if Redis is flushed or goes down? | [Redis: why none of it is authoritative](redis.md#why-none-of-it-is-authoritative) |
| Why does the API exit at boot with `connection refused` on 5432? | [Troubleshooting: `connection refused` on 5432](troubleshooting.md#connection-refused-on-5432) |
| Why does the server fail on Windows with `Event loop is closed`? | [Troubleshooting: psycopg fails on Windows](troubleshooting.md#psycopg-fails-on-windows-proactoreventloop) |
| Why does the CLI or an SDK say `No API key`? | [Troubleshooting: the CLI or an SDK says `No API key`](troubleshooting.md#the-cli-or-an-sdk-says-no-api-key) |
| Why does a key that looks right get `INVALID_API_KEY`? | [Troubleshooting: `INVALID_API_KEY` on a key that looks right](troubleshooting.md#invalid_api_key-on-a-key-that-looks-right) |
| Why did the password-reset or verification email never arrive? | [Troubleshooting: email never arrives](troubleshooting.md#password-reset-or-verification-email-never-arrives) |
| Why does a run fail with `REPLAY_CASSETTE_MISS`? | [Troubleshooting: `REPLAY_CASSETTE_MISS`](troubleshooting.md#replay_cassette_miss) |
| Did my SerpFlow budget run out, or SerpApi's quota? | [Troubleshooting: `BUDGET_EXHAUSTED` against `UPSTREAM_QUOTA_EXHAUSTED`](troubleshooting.md#budget_exhausted-against-upstream_quota_exhausted) |
| Why is nothing ever warm in the cache? | [Troubleshooting: nothing is ever warm](troubleshooting.md#nothing-is-ever-warm) |
| Why does the Kafka producer hang with no error? | [Troubleshooting: producer hangs with no error](troubleshooting.md#producer-hangs-with-no-error) |
| Why does `make demo` exit non-zero? | [Troubleshooting: `make demo` exits non-zero](troubleshooting.md#make-demo-exits-non-zero) |

## Where this section meets the others

| Section | The connection |
| --- | --- |
| [Product](../product/README.md) | the seed loads the [benchmark task set](../product/benchmark.md#the-task-set) and the demo organization the [reference demo](../product/demo.md#what-it-is-proving) runs against; `REPLAY_CASSETTE_MISS` follows from [execution modes: who chooses](../product/execution-modes.md#who-chooses-and-precedence) |
| [Deployment](../deployment/README.md) | the compose services these pages operate: [Docker: Kafka](../deployment/docker.md#kafka), [Docker: Redis](../deployment/docker.md#redis); on a server: [deployment guide, step 12: observability](../deployment/deployment-guide.md#12-observability) and [production: scaling](../deployment/production.md#scaling) |
| [Architecture](../architecture/README.md) | where each service sits and what it is for: [data stores](../architecture/overview.md#data-stores-and-what-each-is-for); what the Redis hot layer may answer: [the Redis boundary](../architecture/caching.md#the-redis-boundary); why the server starts through `app/server.py`: [backend: async on Windows](../architecture/backend.md#async-on-windows) |
| [API](../api/README.md) | `/healthz`, `/readyz` and `/metrics` are [infrastructure endpoints](../api/overview.md#infrastructure); every API error code troubleshooting cites is in [errors](../api/overview.md#errors); the Redis-backed [rate limit](../api/overview.md#rate-limiting) and stream [reconnecting](../api/streaming.md#reconnecting) |
| [SDKs](../sdks/README.md) | the CLI, the Python SDK and the MCP server read `SERPFLOW_API_KEY` from the shell: [SDKs: configuration](../sdks/overview.md#configuration); `make seed` prints the `test` key the [CLI](../sdks/cli.md) uses and the `service` key the [MCP server](../sdks/mcp.md#connect-a-client) uses |
| [Database](../database/README.md) | the bootstrap applies the [Alembic revision chain](../database/migrations.md#the-revision-chain); `make seed ARGS=--reset` is the one sanctioned way past [the append-only audit log](../database/rls.md#the-audit-log); alerts and deliveries are rows in the [governance tables](../database/schema.md#governance) |
| [Security](../security/README.md) | every variable on these pages is in the [secrets inventory](../security/secrets.md#inventory); the log redaction filter is specified in [credentials: never in a log](../security/credentials.md#never-in-a-log); the Redis principal cache sits in [API key resolution](../security/api-keys.md#resolution) |
| [Decisions](../adr/README.md) | the [Kafka page](kafka.md#what-goes-through-it-and-what-does-not) implements ADR 0007; several troubleshooting entries are a decision working as designed, listed [below](#decisions-behind-it) |

## Related

- [Docs index](../README.md): every section, and the end-to-end reading order
- [Glossary](../product/glossary.md): every term in these pages, defined
- [Security](../security/README.md): the previous section, the secrets and keys these pages configure
- [Decisions](../adr/README.md): the next section, the choices behind several of the failures above
- [Local development: troubleshooting](../deployment/local.md#troubleshooting): the problems specific to a laptop setup
- [Deployment guide: operations cheat sheet](../deployment/deployment-guide.md#15-operations-cheat-sheet): status, logs, shells and health on a server

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Secrets](../security/secrets.md) | [Docs index](../README.md) | [Startup bootstrap](../operations/bootstrap.md) |
