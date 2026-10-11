# SDKs

<p>
  <a href="../README.md#sdks"><img alt="docs: SDKs" src="https://img.shields.io/badge/docs-SDKs-8250DF?logo=readthedocs&logoColor=white"></a>
  <img alt="pages: 6" src="https://img.shields.io/badge/pages-6-8250DF">
  <a href="../../sdk/README.md"><img alt="source: sdk/README.md" src="https://img.shields.io/badge/source-sdk%2FREADME.md-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [SDKs](../README.md#sdks) › **SDKs** · page 27 of 57

**The four ways to drive SerpFlow from code besides calling the REST API yourself: a Python SDK, a TypeScript SDK, the `serpflow` CLI and the `serpflow-mcp` server.**

- **After reading it you can pick a client, install it, and call SerpFlow with it:** authenticate with a `sf_test_...` key that spends nothing, plan, search, stream and handle the errors that come back
- **The SDKs are not released yet, by the author's decision:** they will be published to npm and PyPI when the author decides to host SerpFlow ([why](releasing.md#first-who-runs-the-server)). If you self-host, install them from a checkout and use them on your own infrastructure ([Python](python.md#install), [TypeScript](typescript.md#install)); [releasing](releasing.md) is the procedure for that day. Where each package's source lives: [`sdk/README.md`](../../sdk/README.md)
- **Every client needs a SerpFlow you run yourself:** the SDKs and the CLI call its API, and the MCP server connects to its database. SerpFlow is self-hosted for now ([who runs the server](releasing.md#first-who-runs-the-server))
- **New here? Read [SDKs and tools](overview.md) first:** the four surfaces side by side, and [which one to use](overview.md#which-one-to-use)

## Pages

| # | Page | Read it to |
| --- | --- | --- |
| 1 | [SDKs and tools](overview.md) | choose between the four surfaces, and see what each talks to, reads from the shell and can do |
| 2 | [Python SDK](python.md) | call SerpFlow from Python with the sync or async client, or through the SerpApi drop-in |
| 3 | [TypeScript SDK](typescript.md) | do the same from Node, Deno, Bun or a browser, with no runtime dependencies |
| 4 | [CLI](cli.md) | plan, search and inspect from a terminal or a script, and know which commands need the API running |
| 5 | [MCP server](mcp.md) | give an LLM agent four tools, under a session and a budget of its own |
| 6 | [Releasing the SDKs](releasing.md) | publish both SDKs to npm and PyPI, starting with the fixes each needs before its first release |

## Questions this section answers

| If you want to know | Go to |
| --- | --- |
| Which client to use from a Python service or notebook, and how to install it before it is on PyPI | [Python SDK: install](python.md#install) |
| Which client to use from a browser, Node, Deno or Bun, and what the browser needs | [TypeScript SDK: runtimes](typescript.md#runtimes) |
| Which client to use from a shell script or a CI step | [CLI: scripting](cli.md#scripting), with `--json` on `plan` and `search`; for anything else, the REST API ([which one to use](overview.md#which-one-to-use)) |
| Which client to give an AI agent, such as Claude Code or Claude Desktop | [MCP server: connect a client](mcp.md#connect-a-client) |
| Which surfaces need the API running, and which need its database instead | [SDKs and tools: how they connect](overview.md#how-they-connect) |
| Which environment variables each client reads, and why the TypeScript SDK reads none | [SDKs and tools: configuration](overview.md#configuration) |
| Why a `sf_test_...` key spends nothing, and which seeded key goes to which client | [SDKs and tools: test keys](overview.md#test-keys) |
| Which methods the async Python client has, and which are sync-only | [Python SDK: async](python.md#async) |
| How to keep SerpApi call sites while routing through SerpFlow, and what the drop-in actually sends | [Python SDK: the SerpApi drop-in](python.md#the-serpapi-drop-in) |
| How a failed run arrives in a stream, and what leaving the loop early does | [TypeScript SDK: streaming](typescript.md#streaming) |
| Which error codes come with a remedy | [TypeScript SDK: errors](typescript.md#errors) |
| Which `serpflow` commands work with no API, database or key | [CLI: what each command needs](cli.md#what-each-command-needs) |
| How to cap what an agent spends, and why the session cap alone is not a hard limit | [MCP server: sessions and budgets](mcp.md#sessions-and-budgets) |
| Why every MCP call is `INVALID_API_KEY` although the key works with `curl` | [MCP server: troubleshooting](mcp.md#troubleshooting) |
| What has to change before `npm install @serpflow/sdk` or `pip install serpflow` works | [Releasing: before the first TypeScript release](releasing.md#before-the-first-typescript-release) · [before the first Python release](releasing.md#before-the-first-python-release) |
| How to version, build, smoke-test and publish a release | [Releasing: every release](releasing.md#every-release) |

## Where this section meets the others

| Section | The connection |
| --- | --- |
| [Product](../product/README.md) | [the surfaces](../product/product-overview.md#the-surfaces) lists each client beside the REST API and the console, and [who it is for](../product/product-overview.md#who-it-is-for) leads with the SerpApi drop-in and the MCP server; no client sends a per-request mode ([execution modes](../product/execution-modes.md#who-chooses-and-precedence)) |
| [Deployment](../deployment/README.md) | `make install` is the editable install the Python SDK, the CLI and the MCP server come from ([installation: path A](../deployment/installation.md#path-a-developer-install)); [local development: CLI, SDK and MCP](../deployment/local.md#cli-sdk-and-mcp) sets their shell variables; [deployment guide, step 11](../deployment/deployment-guide.md#11-verify-the-deployment) runs the CLI's `health` inside the container |
| [Architecture](../architecture/README.md) | the SDKs and the CLI call the REST API, the MCP server runs the services in-process, and every surface lands in `runs.py` ([the shape of a request](../architecture/overview.md#the-shape-of-a-request)); [backend: error model](../architecture/backend.md#error-model) defines the codes `SerpFlowError` carries |
| [API](../api/README.md) | each SDK method calls a route in [core endpoints](../api/overview.md#core-endpoints), and `SerpFlowError.code` is one of [its errors](../api/overview.md#errors); `stream()` follows the [streaming](../api/streaming.md#clients) contract; [worked examples](../api/examples.md#python-sdk) shows every client in turn |
| [Database](../database/README.md) | the MCP server needs the API's migrated, seeded database rather than its URL, and sets the tenant for [row-level security](../database/rls.md#how-it-works) once its key resolves; `SERPFLOW_MCP_SESSION` names a [`service_sessions`](../database/schema.md#service_sessions) row |
| [Security](../security/README.md) | [test keys](../security/api-keys.md#test-keys) and [service principal sessions](../security/api-keys.md#service-principal-sessions) are what the clients authenticate as; [secrets](../security/secrets.md#cli-sdk-and-mcp-read-from-the-shell) lists the variables they read from the shell; the [threat model](../security/threat-model.md#trust-boundaries) puts the MCP server inside the service boundary |
| [Operations](../operations/README.md) | [seeding by hand](../operations/bootstrap.md#seeding-by-hand) prints the keys and says which goes to which client; troubleshooting covers [a missing key](../operations/troubleshooting.md#the-cli-or-an-sdk-says-no-api-key) in each client and [an MCP agent's session budget](../operations/troubleshooting.md#an-mcp-agents-session-budget-does-not-carry-across-calls) |
| [Decisions](../adr/README.md) | no record is implemented in these pages, but three shape what the clients send and get back, listed [below](#decisions-behind-it) |

## Decisions behind it

- [ADR 0001](../adr/0001-marginal-cost-replanning.md): plans are ranked on marginal cost, so every plan a client receives carries naive and marginal cost, and the flag saying whether cache state changed the winner (`marginal_replan_changed_selection` in Python, `changedSelection` in TypeScript)
- [ADR 0005](../adr/0005-test-key-mode-precedence.md): a `sf_test_...` key routes to the deterministic mock whatever the mode, which is why every client example uses one and spends nothing ([test keys](overview.md#test-keys))
- [ADR 0006](../adr/0006-rls-plus-application-guards.md): tenant isolation is enforced twice, so a project in another organization is `NOT_FOUND` to every client ([Python SDK: recipes](python.md#recipes)), and the MCP server sets the tenant like the API

## Related

- [Docs index](../README.md): every section, and the end-to-end reading order
- [Glossary](../product/glossary.md): every term in these pages, defined
- [API](../api/README.md): the previous section, the HTTP surface every client wraps
- [Database](../database/README.md): the next section, the database the MCP server connects to directly
- [SDK packages](../../sdk/README.md): where each package's source lives, and why the two SDKs sit in different places
- [Troubleshooting: authentication](../operations/troubleshooting.md#authentication): `No API key`, `INVALID_API_KEY` and the other failures a client meets first

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Worked examples](../api/examples.md) | [Docs index](../README.md) | [SDKs and tools](../sdks/overview.md) |
