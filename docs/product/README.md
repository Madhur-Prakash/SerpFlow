# Product

<p>
  <a href="../README.md#product"><img alt="docs: Product" src="https://img.shields.io/badge/docs-Product-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="pages: 5" src="https://img.shields.io/badge/pages-5-2F6BFF">
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [Product](../README.md#product) › **Product** · page 1 of 57

**What SerpFlow is, the one claim it makes, and the measurements that prove it or bound it.**

- **After reading it** you can state the thesis (cache state should change which plan is selected), run the demo that proves it, say which execution mode a search runs in and whether it spends credits, and quote the routing accuracy honestly
- **It is for** anyone evaluating SerpFlow, and anyone about to read the design: these pages are the **why**, [Architecture](../architecture/README.md) is the **how**
- **New here?** Start with the [product overview](product-overview.md), then run [the reference demo](demo.md)

> **Self-hosted, for now, by the author's decision:** there is no hosted instance to sign up for. The author will host one once enough people ask: open a public GitHub issue, or add a thumbs-up to an existing hosting request ([hosting](../../README.md#hosting)).

## Pages

| # | Page | Read it to |
| --- | --- | --- |
| 1 | [Product overview](product-overview.md) | learn what SerpFlow is for, the one claim it makes, and what it deliberately does not do |
| 2 | [The reference demo](demo.md) | see that claim proved in three phases, with an exit code and zero SerpApi credits |
| 3 | [Execution modes](execution-modes.md) | know where a result comes from, whether it costs anything, and who decides |
| 4 | [Routing benchmark](benchmark.md) | know how accurate routing really is (38.3%), and why it fails where it does |
| 5 | [Glossary](glossary.md) | look up any term these docs use, with the page that owns it and, where one exists, its ADR |

## Questions this section answers

| If you want to know | Go to |
| --- | --- |
| What problem does SerpFlow solve, and why do separate fixes not compose? | [Product overview: the problem](product-overview.md#the-problem) |
| What is the one claim, and how could it be proved wrong? | [Product overview: the thesis](product-overview.md#the-thesis) |
| What does SerpFlow deliberately not do? | [Product overview: what it does not do](product-overview.md#what-it-does-not-do) |
| Which surface fits me: REST, SSE, an SDK, the CLI, MCP or the console? | [Product overview: the surfaces](product-overview.md#the-surfaces) |
| What exactly does `make demo` prove, and why is a cache hit not a pass? | [The reference demo: what it is proving](demo.md#what-it-is-proving) |
| Why does the cheaper 11-credit Yelp route never win? | [The reference demo: phase 1](demo.md#phase-1-cold-cache-dry-run) |
| Is the 101-credit chain ever actually spent? | [The reference demo: the full-scale figure](demo.md#the-full-scale-figure) |
| How do I rerun the demo from a genuinely cold state? | [The reference demo: reproducing from a clean state](demo.md#reproducing-from-a-clean-state) |
| What do `live`, `record`, `replay` and `mock` each do, and which spend credits? | [Execution modes: the four modes](execution-modes.md#the-four-modes) |
| Which mode will my search actually run in? | [Execution modes: who chooses, and precedence](execution-modes.md#who-chooses-and-precedence) |
| Who may ask for `live` on a single request? | [Execution modes: permission](execution-modes.md#permission) |
| How do I switch a project to `live`, or back to the instance default? | [Execution modes: setting it](execution-modes.md#setting-it) |
| How accurate is routing, and is 38.3% a ceiling? | [Routing benchmark: read this before quoting the number](benchmark.md#read-this-before-quoting-the-number) |
| Why does the planner pick the wrong engine? | [Routing benchmark: failure analysis](benchmark.md#failure-analysis) |
| How do I re-run the benchmark without overwriting the committed reports? | [Routing benchmark: running it](benchmark.md#running-it) |
| What does a term such as *cassette*, *cold cost* or *coverage* mean? | [Glossary: C](glossary.md#c) |

## Where this section meets the others

| Section | The connection |
| --- | --- |
| [Deployment](../deployment/README.md) | [installation](../deployment/installation.md#3-configure) needs no keys because the default [execution mode](execution-modes.md#the-four-modes) is `replay`; [local development](../deployment/local.md#proving-the-thesis) runs [the reference demo](demo.md), and [optional real searches](../deployment/installation.md#optional-real-searches) switches a project to `live` |
| [Architecture](../architecture/README.md) | the thesis is built in [marginal-cost replanning](../architecture/marginal-replanning.md#worked-example-the-reference-demo), whose worked example is [the reference demo](demo.md); the demo's chain walks [catalog dependency edges](../architecture/catalog.md#the-reference-demo-chain); [the benchmark](benchmark.md) measures [the planner's](../architecture/planner.md) stages A to D |
| [API](../api/README.md) | a per-request `mode` is accepted only on [`POST /v1/search`](../api/overview.md#plan-and-execute) and `POST /v1/plan`, and the resolved mode comes back in [`X-SerpFlow-Mode`](../api/overview.md#provenance-headers); the demo's console pipeline is [the SSE stage sequence](../api/streaming.md#the-stage-sequence) |
| [SDKs](../sdks/README.md) | the [SerpApi drop-in](../sdks/python.md#the-serpapi-drop-in) and [MCP sessions and budgets](../sdks/mcp.md#sessions-and-budgets) are what the [product overview](product-overview.md#who-it-is-for) offers each audience; the SDKs, CLI and MCP send no mode, so they run on the project's ([precedence](execution-modes.md#who-chooses-and-precedence)); [`serpflow benchmark`](../sdks/cli.md#serpflow-benchmark) runs the benchmark |
| [Database](../database/README.md) | a project's own mode arrived in [migration `0004_project_mode`](../database/migrations.md#0004_project_mode); benchmark runs triggered from the UI land in [the benchmark tables](../database/schema.md#benchmark); savings by mechanism are computed from [`budget_ledger`](../database/schema.md#governance) |
| [Security](../security/README.md) | a [test key](../security/api-keys.md#test-keys) always reaches the mock, which is why the demo spends nothing; `live` needs [your own SerpApi key](../security/byok.md), as does the Groq key behind a model-backed benchmark; [replay or mock data mistaken for live](../security/threat-model.md#replay-or-mock-data-mistaken-for-live) is the threat the mode system answers, with its residual risk |
| [Operations](../operations/README.md) | the demo increments [the thesis metric](../operations/observability.md#the-thesis-metric); [troubleshooting: the demo](../operations/troubleshooting.md#the-demo) covers a non-zero exit, and [`REPLAY_CASSETTE_MISS`](../operations/troubleshooting.md#replay_cassette_miss) is `replay` failing loudly |
| [Decisions](../adr/README.md) | the demo exists to prove [ADR 0001](../adr/0001-marginal-cost-replanning.md), and [ADR 0005](../adr/0005-test-key-mode-precedence.md) is why it spends nothing; all five that bear on these pages are listed [below](#decisions-behind-it) |

## Decisions behind it

- [ADR 0001](../adr/0001-marginal-cost-replanning.md): rank candidate plans on marginal cost, not cold cost. The thesis: `make demo` exits non-zero if it stops holding
- [ADR 0002](../adr/0002-deterministic-semantic-guard.md): a deterministic entity and numeral guard, independent of the cosine score. Why a Q3 answer is never served for a Q4 question
- [ADR 0004](../adr/0004-coverage-before-price.md): coverage before price. Why the narrow Yelp route never wins, and the order the benchmark ranks in
- [ADR 0005](../adr/0005-test-key-mode-precedence.md): a test key overrides the execution mode, absolutely. Why the demo and the tests spend zero, and the per-project and per-request update
- [ADR 0006](../adr/0006-rls-plus-application-guards.md): tenant isolation enforced twice. Part of what a platform team gets ([who it is for](product-overview.md#who-it-is-for))

## Related

- [Docs index](../README.md): every section, and the end-to-end reading order
- [Glossary](glossary.md): every term in these pages, defined
- [Deployment](../deployment/README.md): the next section: install it, and run the demo yourself
- [Marginal-cost replanning](../architecture/marginal-replanning.md): the mechanism the thesis rests on
- [Troubleshooting: the demo](../operations/troubleshooting.md#the-demo): when `make demo` exits non-zero
- [Project README](../../README.md): what SerpFlow is, in one page

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Docs index](../README.md) | [Docs index](../README.md) | [Product overview](../product/product-overview.md) |
