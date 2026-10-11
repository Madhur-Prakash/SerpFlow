# Deployment

<p>
  <a href="../README.md#deployment"><img alt="docs: Deployment" src="https://img.shields.io/badge/docs-Deployment-2496ED?logo=readthedocs&logoColor=white"></a>
  <img alt="pages: 5" src="https://img.shields.io/badge/pages-5-2496ED">
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [Deployment](../README.md#deployment) › **Deployment** · page 7 of 50

**Getting SerpFlow running: on a laptop, entirely in Docker, or on a server you control.**

- **After reading it** you can install SerpFlow with no API keys, verify the install, work on it every day, and run it on a server behind TLS with real secrets
- **It is for** developers setting up a checkout, and operators putting it on a host
- **New here?** Start with [installation](installation.md): it routes you to the developer path or the Docker path, then [verifies the install](installation.md#verify-the-install)

> **There is no hosted SerpFlow to sign up for:** it is self-hosted for now, by the author's decision. The author will host it once enough people ask: open a public GitHub issue, or add a thumbs-up to an existing hosting request ([hosting](../../README.md#hosting)).

## Pages

| # | Page | Read it to |
| --- | --- | --- |
| 1 | [Installation](installation.md) | go from a blank machine to a running, verified install, on either path, with no API keys |
| 2 | [Local development](local.md) | work on it daily: every `make` target, modes, real keys, and the CLI, SDK and MCP environment |
| 3 | [Docker](docker.md) | know what each container, image, profile, port and volume is, and the `/docs` known issue |
| 4 | [Deployment guide](deployment-guide.md) | put it on one server, step by step: secrets, ports, RLS, TLS, first admin, backups, upgrades |
| 5 | [Production](production.md) | harden it and scale past one host: pre-flight checks, pooling, Kafka topology, retention |

## Questions this section answers

| If you want to know | Go to |
| --- | --- |
| **Which page do I need on a developer laptop**, to change the code? | [Installation: path A, developer install](installation.md#path-a-developer-install) |
| **Which page do I need to run all of it in Docker**, without changing the code? | [Installation: path B, everything in Docker](installation.md#path-b-everything-in-docker) |
| **Which page do I need to put it on a server?** | [Deployment guide: 1. Prepare the server](deployment-guide.md#1-prepare-the-server) |
| What changes once it runs on more than one host? | [Production: scaling](production.md#scaling) |
| What must be installed first, on Linux, macOS or Windows? | [Installation: 1. Prerequisites](installation.md#1-prerequisites) |
| How do I prove the install works, from `/readyz` to `make demo`? | [Installation: verify the install](installation.md#verify-the-install) |
| Where are the API keys, and why did `make seed` print none? | [Local development: first run](local.md#first-run) |
| Why do the CLI, the SDK and the MCP server ignore my `.env`? | [Local development: CLI, SDK and MCP](local.md#cli-sdk-and-mcp) |
| What does each `make` target run? | [Local development: everyday targets](local.md#everyday-targets) |
| How do I run real SerpApi searches on my own machine? | [Local development: using real keys](local.md#using-real-keys) |
| A port is already in use: which can I move, and why not Kafka's on its own? | [Docker: running](docker.md#running) |
| Why does `/docs/readme` return a JSON 404 in the container stack? | [Docker: known issue, `/docs` deep links](docker.md#known-issue-docs-deep-links) |
| Which secrets must I generate, and what breaks if I lose one? | [Deployment guide: 3. Generate secrets](deployment-guide.md#3-generate-secrets) |
| Why does row-level security not bind on the bundled stack, and how do I make it? | [Deployment guide: 8. Make row-level security bind](deployment-guide.md#8-make-row-level-security-bind) |
| How do I back up, and prove a restore lost nothing? | [Deployment guide: 13. Backups](deployment-guide.md#13-backups) |
| What must be true before it holds anybody's real SerpApi credentials? | [Production: before anything else](production.md#before-anything-else) |

## Where this section meets the others

| Section | The connection |
| --- | --- |
| [Product](../product/README.md) | the install needs no keys because the default [execution mode](../product/execution-modes.md#the-four-modes) is `replay`; [verifying the install](installation.md#verify-the-install) ends with [the reference demo](../product/demo.md); real searches mean [setting a project to `live`](../product/execution-modes.md#setting-it) |
| [Architecture](../architecture/README.md) | `make backend` and the container both start [`app.server`](../architecture/backend.md#async-on-windows), not uvicorn directly; `STORAGE_BACKEND` chooses the [object storage](../architecture/caching.md#object-storage); [production: scaling](production.md#scaling) rests on [the data stores](../architecture/overview.md#data-stores-and-what-each-is-for) holding all state |
| [API](../api/README.md) | `make api-check` [calls every operation](../api/overview.md#checking-every-operation); a proxy in front must not buffer [the stream](../api/streaming.md#behind-a-proxy); [rate limiting](../api/overview.md#rate-limiting) is per principal and path, so `TRUSTED_PROXY_HOPS` does not affect it |
| [SDKs](../sdks/README.md) | `make install` puts the [CLI](../sdks/cli.md#install), the [Python SDK](../sdks/python.md#install) and the [MCP server](../sdks/mcp.md#connect-a-client) in the venv; they read the shell, not `.env` ([local development](local.md#cli-sdk-and-mcp)); `make health` is [`serpflow health`](../sdks/cli.md#serpflow-health) |
| [Database](../database/README.md) | `make upgrade` applies [the revision chain](../database/migrations.md#the-revision-chain); [step 8](deployment-guide.md#8-make-row-level-security-bind) and [production](production.md#before-anything-else) make [row-level security](../database/rls.md#verifying-it) bind, which the bundled superuser connection defeats |
| [Security](../security/README.md) | [step 3](deployment-guide.md#3-generate-secrets) generates what [secrets](../security/secrets.md#generating-real-ones) inventories, checked against [the production checklist](../security/secrets.md#production-checklist); upstream keys are [brought per organization](../security/byok.md), and a `GROQ_API_KEY` in `.env` is [the self-hosting exception](../security/byok.md#the-self-hosting-exception) |
| [Operations](../operations/README.md) | the API [migrates and seeds itself on start](../operations/bootstrap.md), and [refuses to seed in production](../operations/bootstrap.md#3-an-environment-refusal); [health](../operations/observability.md#health) backs the probes; [Kafka: listeners](../operations/kafka.md#listeners) explains the two advertised addresses; [troubleshooting: deployment](../operations/troubleshooting.md#deployment) lists the failures these pages prevent |
| [Decisions](../adr/README.md) | [ADR 0013](../adr/0013-explicit-event-loop-factory.md) is why every start goes through `app.server`; [ADR 0006](../adr/0006-rls-plus-application-guards.md) is why the application's role must not own the tables; [ADR 0003](../adr/0003-envelope-encryption.md) is why losing `CREDENTIAL_KEK` loses every stored credential |

## Related

- [Docs index](../README.md): every section, and the end-to-end reading order
- [Glossary](../product/glossary.md): every term in these pages, defined
- [Product](../product/README.md): the previous section: what you are installing, and the demo that proves it
- [Architecture](../architecture/README.md): the next section: the system these containers run
- [Troubleshooting](../operations/troubleshooting.md): setup, database, Kafka and deployment failures, each with its fix
- [Secrets: production checklist](../security/secrets.md#production-checklist): the same pre-launch checks, from the security side

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Glossary](../product/glossary.md) | [Docs index](../README.md) | [Installation](../deployment/installation.md) |
