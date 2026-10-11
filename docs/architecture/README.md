# Architecture

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="pages: 9" src="https://img.shields.io/badge/pages-9-2F6BFF">
  <img alt="read: 7 min" src="https://img.shields.io/badge/read-7%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **Architecture** · page 13 of 50

**How an intent becomes a plan, why cache state can change which plan that is, and how the chosen plan runs.**

- **After reading it you can follow one request end to end:** authentication, the four planner stages, the cost model, the four cache layers, and the `runs` row and `complete` frame at the end
- **It is for anyone changing the planner, the cache or the executor**, or explaining why a run chose the plan it did
- **New here? Read the [overview](overview.md) first**, then [marginal-cost replanning](marginal-replanning.md): the thesis every other page in this folder exists to serve

## Pages

| # | Page | Read it to |
| --- | --- | --- |
| 1 | [Architecture overview](overview.md) | see the shape of a request, its lifecycle, the layers, the data stores, execution modes and tenancy |
| 2 | [The engine catalog](catalog.md) | learn what an engine entry declares, why chaining and competing are separate edge sets, and how the YAML is authored, loaded and versioned |
| 3 | [The planner](planner.md) | follow stages A to D, from 54 engines to a set of competing candidate plans, and see what the Plan stores |
| 4 | [Marginal-cost replanning](marginal-replanning.md) | see how every candidate is costed against warm cache, ranked twice, and reduced to fit a budget |
| 5 | [Caching](caching.md) | learn the four layers, partitioning, the entity and numeral guard, adaptive TTL and invalidation |
| 6 | [The executor](executor.md) | see how the selected plan runs, where the credential is decrypted, and what each step and run records |
| 7 | [Backend](backend.md) | find a module, the middleware order, the error envelope, and how each dependency degrades |
| 8 | [Frontend](frontend.md) | see how the console renders the pipeline, the inspectors and every route under `/app` |
| 9 | [The public web surface](web.md) | understand the landing page, the theme, the docs browser and its link resolution, and the generated API reference |

**How a request flows through these pages:**

```
intent            REST, SDKs, CLI, MCP -> plan_and_execute         overview.md
 -> catalog       54 engines: how they chain, how they compete     catalog.md
 -> planner       stages A-D -> N candidate plans                  planner.md
 -> marginal      cost each step on warm, fresh-enough cache;      marginal-replanning.md
    replanning    re-rank; reduce to fit the budget
 -> caching       inspect() for the planner, lookup() and          caching.md
                  store() for the executor
 -> executor      exact -> semantic -> archive -> live             executor.md
```

- **Around that path:** [backend](backend.md) is the package and middleware it runs in, [frontend](frontend.md) is the console that renders it, and [web](web.md) is the public pages, outside the request path

## Questions this section answers

| If you want to know | Go to |
| --- | --- |
| What happens, in order, when `POST /v1/search` arrives | [Architecture overview: request lifecycle](overview.md#request-lifecycle) |
| Which execution mode wins when the key, the request, the project and the instance disagree | [Architecture overview: execution modes](overview.md#execution-modes) |
| Why dependency and substitute edges are kept apart, and what breaks without either | [The engine catalog: both relationship kinds are mandatory](catalog.md#both-relationship-kinds-are-mandatory) |
| How an engine gets into the catalog, and which steps need a person | [The engine catalog: how the catalog is authored](catalog.md#how-the-catalog-is-authored) |
| Which adapter selects engines, and what happens without a Groq key | [The planner: which adapter plans](planner.md#which-adapter-plans) |
| Why a Google Finance step sends a ticker, not the sentence | [The planner: query adapters](planner.md#query-adapters) |
| Why a cached entry can be available and still not count as warm | [Marginal-cost replanning: available is not acceptable](marginal-replanning.md#available-is-not-acceptable) |
| What `changed_selection` records, and when it is true | [Marginal-cost replanning: what `changed_selection` means](marginal-replanning.md#what-changed_selection-means) |
| What the planner does when no candidate fits the budget | [Marginal-cost replanning: when nothing fits](marginal-replanning.md#when-nothing-fits) |
| Why `iphone 16` never matches a cached `iphone 17`, whatever the similarity | [Caching: the entity and numeral guard](caching.md#the-entity-and-numeral-guard) |
| Whether a test key's mock data can serve a later live run | [Caching: execution mode is not part of the key](caching.md#execution-mode-is-not-part-of-the-key) |
| What happens when a credential is revoked part-way through a run | [The executor: revocation mid-run](executor.md#revocation-mid-run) |
| What a failed run keeps, and what it cost | [The executor: when a run fails](executor.md#when-a-run-fails) |
| What still works when Redis, Kafka or object storage is down | [Backend: degradation](backend.md#degradation) |
| Whether the search page's pipeline animation is real progress | [Frontend: the pipeline animation](frontend.md#the-pipeline-animation) |
| How one markdown link works both on GitHub and in the app's docs browser | [The public web surface: how links resolve](web.md#how-links-resolve) |

## Where this section meets the others

| Section | The connection |
| --- | --- |
| [Product](../product/README.md) | these pages build what [the thesis](../product/product-overview.md#the-thesis) promises; the [worked example](marginal-replanning.md#worked-example-the-reference-demo) derives the numbers [the reference demo](../product/demo.md#the-three-phases) proves; the [execution modes](../product/execution-modes.md) are applied where [LIVE goes](executor.md#where-live-goes) |
| [Deployment](../deployment/README.md) | `make demo` in [proving the thesis](../deployment/local.md#proving-the-thesis) runs the replanning worked example; [production: retention](../deployment/production.md#retention) sets the windows the [executor](executor.md#retention) stamps; the [`/docs` deep-link issue](../deployment/docker.md#known-issue-docs-deep-links) affects the [docs browser](web.md#how-links-resolve) |
| [API](../api/README.md) | the [API overview](../api/overview.md) is the HTTP surface at the top of [the shape of a request](overview.md#the-shape-of-a-request); [the stage sequence](../api/streaming.md#the-stage-sequence) is published by the [planner](planner.md) and the [executor](executor.md); the `/api` reference is [generated](web.md#the-api-reference) from the OpenAPI schema |
| [SDKs](../sdks/README.md) | the SDKs and CLI reach `plan_and_execute` through REST and the MCP server calls it in-process ([how they connect](../sdks/overview.md#how-they-connect)); all of them are packaged in the backend ([module map](backend.md#module-map)) |
| [Database](../database/README.md) | the planner writes [`plans` and `plan_candidates`](../database/schema.md#planning-and-execution), caching reads and writes the [cache tables](../database/schema.md#cache), and the [request lifecycle](backend.md#request-lifecycle) binds [row-level security](../database/rls.md#how-it-works) per transaction |
| [Security](../security/README.md) | the [credential boundary](executor.md#the-credential-boundary) is [where a credential is decrypted](../security/credentials.md#where-it-is-decrypted); [tenancy](overview.md#tenancy) maps to the [trust boundaries](../security/threat-model.md#trust-boundaries); the [frontend](frontend.md#permissions) mirrors the [roles](../security/api-keys.md#roles) the server enforces |
| [Operations](../operations/README.md) | [the thesis metric](../operations/observability.md#the-thesis-metric) counts [changed selections](marginal-replanning.md#what-changed_selection-means); [Redis](../operations/redis.md#why-none-of-it-is-authoritative) is the hot layer behind [the Redis boundary](caching.md#the-redis-boundary); [Kafka](../operations/kafka.md#topics) carries background work only, and [degradation](backend.md#degradation) says what happens when either is down |

## Related

- [Docs index](../README.md): every section, and the end-to-end reading order
- [Glossary](../product/glossary.md): every term in these pages, defined
- [Deployment](../deployment/README.md): the previous section, for installing and running what these pages describe
- [API](../api/README.md): the next section, the HTTP and SSE contracts at the top of the request path
- [The reference demo](../product/demo.md): the whole request path run three times, with the thesis asserted
- [Troubleshooting](../operations/troubleshooting.md#execution): cassette misses, budget errors, revoked credentials and the other failures these pages explain

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Production](../deployment/production.md) | [Docs index](../README.md) | [Architecture overview](../architecture/overview.md) |
