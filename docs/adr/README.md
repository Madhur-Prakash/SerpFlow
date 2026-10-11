# Architecture decision records

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="records: 14" src="https://img.shields.io/badge/records-14-555555">
  <img alt="status: all accepted" src="https://img.shields.io/badge/status-all%20accepted-3fcf8e">
  <a href="../../backend/app/services/planner/cost.py"><img alt="source: planner/cost.py" src="https://img.shields.io/badge/source-planner%2Fcost.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **Architecture decision records** · page 43 of 57

**The decisions that were not obvious**, with the reasoning that produced them and the thing that was given up.

- **An ADR is here when the alternative was genuinely defensible**
  - "we used PostgreSQL" is not a decision record
  - "we rank on coverage before price, which means a cheaper plan can lose" is

| # | Decision | Area | Implemented in | Status |
| --- | --- | --- | --- | --- |
| [0001](0001-marginal-cost-replanning.md) | Rank candidate plans on marginal cost, not cold cost | planner | [ranking](../architecture/marginal-replanning.md#ranking) · [`cost.py`](../../backend/app/services/planner/cost.py) | Accepted |
| [0002](0002-typed-catalog-edges.md) | Two separate edge sets: dependency and substitute | catalog | [the catalog](../architecture/catalog.md#both-relationship-kinds-are-mandatory) · [`loader.py`](../../backend/app/services/catalog/loader.py) | Accepted |
| [0003](0003-deterministic-semantic-guard.md) | A deterministic guard independent of the cosine score | cache | [the guard](../architecture/caching.md#the-entity-and-numeral-guard) · [`guard.py`](../../backend/app/services/cache/guard.py) | Accepted |
| [0004](0004-hmac-for-api-keys.md) | HMAC-SHA256 for API keys, Argon2id for passwords | security | [API key hashing](../security/api-keys.md#hashing-hmac-sha256-not-argon2) · [`security.py`](../../backend/app/core/security.py) | Accepted |
| [0005](0005-envelope-encryption.md) | Envelope encryption for upstream credentials | security | [envelope encryption](../security/credentials.md#envelope-encryption) · [`security.py`](../../backend/app/core/security.py) | Accepted |
| [0006](0006-no-credential-field-in-schemas.md) | The credential field is absent from schemas, not excluded | security | [never in a response](../security/credentials.md#never-in-a-response) · [`identity.py`](../../backend/app/schemas/identity.py) | Accepted |
| [0007](0007-interactive-search-bypasses-kafka.md) | Interactive search does not go through Kafka | runtime | [what goes through Kafka](../operations/kafka.md#what-goes-through-it-and-what-does-not) · [`search.py`](../../backend/app/api/v1/search.py) | Accepted |
| [0008](0008-coverage-before-price.md) | Rank on coverage before price | planner | [coverage before price](../architecture/marginal-replanning.md#coverage-before-price) · [`cost.py`](../../backend/app/services/planner/cost.py) | Accepted |
| [0009](0009-freshness-gates-warmth.md) | Available is not acceptable: freshness gates warmth | cache | [available is not acceptable](../architecture/marginal-replanning.md#available-is-not-acceptable) · [`text.py`](../../backend/app/core/text.py) | Accepted |
| [0010](0010-test-key-mode-precedence.md) | A test key overrides the execution mode, absolutely | execution | [mode precedence](../product/execution-modes.md#who-chooses-and-precedence) · [`serpapi/__init__.py`](../../backend/app/integrations/serpapi/__init__.py) | Accepted |
| [0011](0011-rls-plus-application-guards.md) | Tenant isolation enforced twice | tenancy | [row-level security](../database/rls.md#how-it-works) · [`deps.py`](../../backend/app/api/deps.py) | Accepted |
| [0012](0012-append-only-audit-log.md) | The audit log is append-only in the database | governance | [the audit log](../database/rls.md#the-audit-log) · [`audit/service.py`](../../backend/app/services/audit/service.py) | Accepted |
| [0013](0013-explicit-event-loop-factory.md) | Run uvicorn through an explicit loop factory | runtime | [async on Windows](../architecture/backend.md#async-on-windows) · [`server.py`](../../backend/app/server.py) | Accepted |
| [0014](0014-persist-every-candidate.md) | Persist every candidate plan, not just the winner | planner | [what the Plan stores](../architecture/planner.md#what-the-plan-stores) · [`planning.py`](../../backend/app/db/models/planning.py) | Accepted |

## How they fit together

**Six of the fourteen are one argument**, the thesis that warm cache state should change which plan runs:

```
inputs     0002 typed catalog edges       several candidate chains exist at all
           0003 deterministic guard       which cache hits are safe
           0009 freshness gates warmth    which safe hits count as warm
                        │
                        ▼
decision   0001 rank on marginal cost     price only the steps that are still cold
           0008 coverage before price     the key sorted ahead of that price
                        │
                        ▼
evidence   0014 persist every candidate   the comparison, stored so it can be audited
```

- **Security (0004, 0005, 0006):** one secret hashed, one encrypted, and the decrypted one kept out of every response. Read with the [threat model](../security/threat-model.md#threats-and-responses)
- **Tenancy and governance (0011, 0012):** isolation enforced in the database and the application, and an audit log the application cannot rewrite. Read with [row-level security](../database/rls.md)
- **Runtime and execution (0007, 0010, 0013):** what stays in-process, which mode a request runs in, and how the server starts on every platform. Read with the [backend](../architecture/backend.md) and [execution modes](../product/execution-modes.md)

## Format

Every record has the same five parts:

| Part | Answers |
| --- | --- |
| **Context** | what forced a decision |
| **Decision** | what was chosen, concretely |
| **Alternatives rejected** | what else was defensible, and why it lost |
| **Cost** | what the choice gives up |
| **See also** | where it lives in the code and the docs |

- **The cost section is not decoration:** a decision with no downside was not a decision
- **Records are not rewritten when the code moves on.** A dated **Update (YYYY-MM-DD)** note goes at the end of the Decision or Cost section, saying what changed and where; the decision, its status and its date stay as they were

## Writing a new one

- **Copy the shape above**, number it next in sequence, and add it to the table, with the page and the code that implement it
- Add it to `ORDER` in [`scripts/build_docs_nav.py`](../../scripts/build_docs_nav.py), then run [`make docs-nav`](../deployment/local.md#everyday-targets), which regenerates every page's header and previous/next links, and `make docs-check`
- **Link it both ways:** from the page that implements the decision, and from the See also of every related record

## Related

- [Architecture overview](../architecture/overview.md): the system the decisions shape, with links into each layer
- [Product overview](../product/product-overview.md): the thesis the planner and cache records exist to defend
- [Threat model](../security/threat-model.md#threats-and-responses): where the security and tenancy records meet the threats they answer, and their stated limits
- [Glossary](../product/glossary.md): one-line definitions of the terms these records use, each with its ADR
- [Troubleshooting](../operations/troubleshooting.md): the failures several of these decisions choose deliberately, such as `REPLAY_CASSETTE_MISS`
- [Contributing: changing the docs](../../CONTRIBUTING.md#changing-the-docs): when a decision earns a record, and the house rules for writing one
- [Documentation index](../README.md): every page, in reading order
- [Project README](../../README.md): what SerpFlow is, in one page

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Troubleshooting](../operations/troubleshooting.md) | [Docs index](../README.md) | [ADR 0001: Rank candidate plans on marginal cost, n…](../adr/0001-marginal-cost-replanning.md) |
