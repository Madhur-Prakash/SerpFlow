# Architecture decision records

**The six decisions that were not obvious**, with the reasoning that produced them and the thing that was given up.

- **An ADR is here when the alternative was genuinely defensible**
  - "we used PostgreSQL" is not a decision record
  - "we rank on coverage before price, which means a cheaper plan can lose" is
- **The architecture pages say how SerpFlow works; these say why it does not work the other way.** Each record links to the page that implements it
- **Every other section lists the decisions behind it**, under "Decisions behind it" in its index: [Product](../product/README.md) · [Deployment](../deployment/README.md) · [Architecture](../architecture/README.md) · [API](../api/README.md) · [SDKs](../sdks/README.md) · [Database](../database/README.md) · [Security](../security/README.md) · [Operations](../operations/README.md)

| # | Decision | Area | Implemented in | Status |
| --- | --- | --- | --- | --- |
| [0001](0001-marginal-cost-replanning.md) | Rank candidate plans on marginal cost, not cold cost | planner | [ranking](../architecture/marginal-replanning.md#ranking) · [`cost.py`](../../backend/app/services/planner/cost.py) | Accepted |
| [0003](0003-deterministic-semantic-guard.md) | A deterministic guard independent of the cosine score | cache | [the guard](../architecture/caching.md#the-entity-and-numeral-guard) · [`guard.py`](../../backend/app/services/cache/guard.py) | Accepted |
| [0005](0005-envelope-encryption.md) | Envelope encryption for upstream credentials | security | [envelope encryption](../security/credentials.md#envelope-encryption) · [`security.py`](../../backend/app/core/security.py) | Accepted |
| [0008](0008-coverage-before-price.md) | Rank on coverage before price | planner | [coverage before price](../architecture/marginal-replanning.md#coverage-before-price) · [`cost.py`](../../backend/app/services/planner/cost.py) | Accepted |
| [0010](0010-test-key-mode-precedence.md) | A test key overrides the execution mode, absolutely | execution | [mode precedence](../product/execution-modes.md#who-chooses-and-precedence) · [`serpapi/__init__.py`](../../backend/app/integrations/serpapi/__init__.py) | Accepted |
| [0011](0011-rls-plus-application-guards.md) | Tenant isolation enforced twice | tenancy | [row-level security](../database/rls.md#how-it-works) · [`deps.py`](../../backend/app/api/deps.py) | Accepted |

- **Numbers are permanent identifiers**, so the sequence has gaps: a record keeps its number for as long as it is kept

## How they fit together

**Three of the six are one argument**, the thesis that warm cache state should change which plan runs:

```
input      0003 deterministic guard       which cache hits are safe to count as warm
                        │
                        ▼
decision   0008 coverage before price     the key sorted first: a cheaper plan that covers less loses
           0001 rank on marginal cost     then price only the steps that are still cold
```

- **Security (0005):** the one secret that must be recoverable, encrypted so a database dump alone reveals nothing. Read with the [threat model](../security/threat-model.md#threats-and-responses)
- **Tenancy (0011):** isolation enforced in the application and again in PostgreSQL. Read with [row-level security](../database/rls.md), including why a superuser connection defeats the second half
- **Execution (0010):** a test key always means mock data, whatever else is configured. Read with [execution modes](../product/execution-modes.md)

## Format

Every record has the same five parts:

| Part | Answers |
| --- | --- |
| **Context** | what forced a decision |
| **Decision** | what was chosen, concretely |
| **Alternatives rejected** | what else was defensible, and why it lost |
| **Cost** | what the choice gives up |
| **Related** | where it lives in the code and the docs |

- **The cost section is not decoration:** a decision with no downside was not a decision
- **Records are not rewritten when the code moves on.** A dated **Update (YYYY-MM-DD)** note goes at the end of the Decision or Cost section, saying what changed and where; the decision, its status and its date stay as they were

## Writing a new one

- **Only for a decision whose alternative was genuinely defensible.** Copy the shape above, number it after the highest number used, and add it to the table with the page and the code that implement it
- Add it to `ORDER` in [`scripts/build_docs_nav.py`](../../scripts/build_docs_nav.py), then run [`make docs-nav`](../deployment/local.md#everyday-targets), which regenerates every page's header and previous/next links, and `make docs-check`
- **Link it both ways:** from the page that implements the decision, from the "Decisions behind it" list of each section index it bears on, and from the Related list of every related record

## Related

- [Architecture overview](../architecture/overview.md): the system the decisions shape, with links into each layer
- [Product overview](../product/product-overview.md): the thesis records 0001, 0003 and 0008 exist to defend
- [Marginal-cost replanning](../architecture/marginal-replanning.md): where 0001 and 0008 are implemented, with the worked example
- [Threat model](../security/threat-model.md#threats-and-responses): where 0005 and 0011 meet the threats they answer, and their stated limits
- [Glossary](../product/glossary.md): one-line definitions of the terms these records use
- [Troubleshooting](../operations/troubleshooting.md): the failures some of these decisions choose deliberately, such as `REPLAY_CASSETTE_MISS`
- [Documentation index](../README.md): every page, in reading order
