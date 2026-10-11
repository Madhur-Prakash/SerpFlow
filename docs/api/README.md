# API

<p>
  <a href="../README.md#api"><img alt="docs: API" src="https://img.shields.io/badge/docs-API-009688?logo=readthedocs&logoColor=white"></a>
  <img alt="pages: 3" src="https://img.shields.io/badge/pages-3-009688">
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [API](../README.md#api) › **API** · page 23 of 57

**The HTTP and SSE contract every client is built on: authentication, all 85 operations, the stream of stage frames, and worked requests.**

- **After reading it you can call SerpFlow over HTTP:** authenticate, plan without spending, run a search, tail its stages, and read the provenance headers and error codes that come back
- **Want a client library instead? The Python and TypeScript SDKs, the CLI and the MCP server wrap these routes:** see [SDKs](../sdks/README.md)
- **The app also serves a generated reference at `/api`:** every operation, read from the OpenAPI schema by `make api-reference` and rerun after a router changes. How it is built: [the API reference](../architecture/web.md#the-api-reference). The API server itself serves Swagger UI at `/docs` and ReDoc at `/redoc` ([API overview](overview.md))
- **New here? Read [authentication](overview.md#authentication) first**, then run [plan without spending](examples.md#plan-without-spending) with a test key: zero SerpApi credits

## Pages

| # | Page | Read it to |
| --- | --- | --- |
| 1 | [API overview](overview.md) | authenticate, find any of the 85 operations and the permission it needs, and read the headers, errors, pagination and rate limits |
| 2 | [Streaming](streaming.md) | start a streamed search, read its eleven stages frame by frame, reconnect, and keep it working behind a proxy |
| 3 | [Worked examples](examples.md) | copy working requests for planning, searching, streaming, the catalog and false-hit reports, plus each client and the SerpApi drop-in, all on a test key |

## Questions this section answers

| If you want to know | Go to |
| --- | --- |
| How to authenticate, and which project a request acts in | [API overview: authentication](overview.md#authentication) |
| Which permission an operation needs, and which role holds it | [API overview: who can call what](overview.md#who-can-call-what) |
| What a search would cost, without spending a credit | [API overview: plan without executing](overview.md#plan-without-executing) |
| Which cache layer served a response, and in which mode it ran | [API overview: provenance headers](overview.md#provenance-headers) |
| What an error code means, and what to do about it | [API overview: errors](overview.md#errors) |
| Which routes are rate limited, and how the window resets | [API overview: rate limiting](overview.md#rate-limiting) |
| How to start a search you can watch | [Streaming: starting a run you can stream](streaming.md#starting-a-run-you-can-stream) |
| Which stages arrive, in what order, and who produces each | [Streaming: the stage sequence](streaming.md#the-stage-sequence) |
| How to resume a stream after a dropped connection | [Streaming: reconnecting](streaming.md#reconnecting) |
| How a browser `EventSource`, which cannot set headers, authenticates | [Streaming: authentication](streaming.md#authentication) |
| Why frames arrive all at once behind nginx or Caddy | [Streaming: behind a proxy](streaming.md#behind-a-proxy) |
| What a billed search that found nothing returns | [Worked examples: a search that found nothing](examples.md#a-search-that-found-nothing) |
| How to report a semantic hit that returned the wrong thing | [Worked examples: report a bad semantic hit](examples.md#report-a-bad-semantic-hit) |
| How to move existing SerpApi code onto SerpFlow without rewriting it | [Worked examples: the SerpApi drop-in](examples.md#the-serpapi-drop-in) |
| How to connect an agent through the MCP server | [Worked examples: MCP](examples.md#mcp) |

## Where this section meets the others

| Section | The connection |
| --- | --- |
| [Product](../product/README.md) | [execution modes](../product/execution-modes.md#who-chooses-and-precedence) decide the `X-SerpFlow-Mode` on every response, and why every [worked example](examples.md) is `MOCK`; [the reference demo](../product/demo.md#the-three-phases) shows why a [replayed run](overview.md#runs) can select a different plan |
| [Deployment](../deployment/README.md) | `make seed` in [first run](../deployment/local.md#first-run) prints the test key the examples use; [behind a reverse proxy](../deployment/production.md#behind-a-reverse-proxy) and [put TLS in front](../deployment/deployment-guide.md#9-put-tls-in-front) keep the [stream](streaming.md#behind-a-proxy) unbuffered |
| [Architecture](../architecture/README.md) | every call runs the [request lifecycle](../architecture/overview.md#request-lifecycle); the [planner](../architecture/planner.md) and [executor](../architecture/executor.md) publish the [stage frames](streaming.md#the-stage-sequence); the [error model](../architecture/backend.md#error-model) implements the envelope; [the API reference](../architecture/web.md#the-api-reference) generates `/api` |
| [SDKs](../sdks/README.md) | [SDKs and tools](../sdks/overview.md) wrap these routes; [Python](../sdks/python.md#streaming) and [TypeScript](../sdks/typescript.md#streaming) streaming consume the same frames; the [CLI](examples.md#cli) and [MCP](examples.md#mcp) examples start here and continue in [CLI](../sdks/cli.md) and [MCP server](../sdks/mcp.md#connect-a-client) |
| [Database](../database/README.md) | the Plan that `POST /v1/plan` returns is persisted as [`plans` and `plan_candidates`](../database/schema.md#planning-and-execution) rows; the savings waterfall sums [`budget_ledger`](../database/schema.md#budget_ledger); a cross-tenant id is `NOT_FOUND` because of [the application guards](../database/rls.md#the-application-guards); `/v1/audit/verify` walks [the audit log](../database/rls.md#the-audit-log) |
| [Security](../security/README.md) | [roles](../security/api-keys.md#roles) are the permissions printed next to every operation; the [key format](../security/api-keys.md#format) and [test keys](../security/api-keys.md#test-keys) are what `X-API-Key` carries; the credential routes manage [upstream credentials](../security/credentials.md#validation-and-revocation), which no response ever returns |
| [Operations](../operations/README.md) | [troubleshooting](../operations/troubleshooting.md#authentication) fixes the error codes; [correlating one request](../operations/observability.md#correlating-one-request) follows a `request_id`; [what goes through Kafka](../operations/kafka.md#what-goes-through-it-and-what-does-not) explains why an interactive search never does; [Redis](../operations/redis.md#what-lives-in-it) holds the rate-limit counters and the stream mirror |
| [Decisions](../adr/README.md) | the records these routes enforce, listed [below](#decisions-behind-it) |

## Decisions behind it

- [ADR 0002](../adr/0002-deterministic-semantic-guard.md): the guard behind `GET /v1/cache/guard-rejections`, and why a [false-hit report](examples.md#report-a-bad-semantic-hit) is evidence
- [ADR 0005](../adr/0005-test-key-mode-precedence.md): a test key always routes to the deterministic mock, which is why every [worked example](examples.md) spends nothing
- [ADR 0006](../adr/0006-rls-plus-application-guards.md): a cross-tenant id returns `NOT_FOUND`, so its existence is never confirmed ([errors](overview.md#errors))

## Related

- [Docs index](../README.md): every section, and the end-to-end reading order
- [Glossary](../product/glossary.md): every term in these pages, defined
- [Architecture](../architecture/README.md): the previous section, what runs behind each route
- [SDKs](../sdks/README.md): the next section, the clients that wrap these routes
- [Execution modes](../product/execution-modes.md): why a response says `LIVE`, `RECORD`, `REPLAY` or `MOCK`, and who chooses
- [Troubleshooting](../operations/troubleshooting.md): fixes for the error codes these routes return

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [The public web surface](../architecture/web.md) | [Docs index](../README.md) | [API overview](../api/overview.md) |
