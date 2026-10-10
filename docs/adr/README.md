# Architecture decision records

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="records: 14" src="https://img.shields.io/badge/records-14-555555">
  <img alt="status: all accepted" src="https://img.shields.io/badge/status-all%20accepted-3fcf8e">
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **Architecture decision records** · page 36 of 50

**The decisions that were not obvious**, with the reasoning that produced them and the thing that was given up.

- **An ADR is here when the alternative was genuinely defensible**
  - "we used PostgreSQL" is not a decision record
  - "we rank on coverage before price, which means a cheaper plan can lose" is

| # | Decision | Area | Status |
| --- | --- | --- | --- |
| [0001](0001-marginal-cost-replanning.md) | Rank candidate plans on marginal cost, not cold cost | planner | Accepted |
| [0002](0002-typed-catalog-edges.md) | Two separate edge sets: dependency and substitute | catalog | Accepted |
| [0003](0003-deterministic-semantic-guard.md) | A deterministic guard independent of the cosine score | cache | Accepted |
| [0004](0004-hmac-for-api-keys.md) | HMAC-SHA256 for API keys, Argon2id for passwords | security | Accepted |
| [0005](0005-envelope-encryption.md) | Envelope encryption for upstream credentials | security | Accepted |
| [0006](0006-no-credential-field-in-schemas.md) | The credential field is absent from schemas, not excluded | security | Accepted |
| [0007](0007-interactive-search-bypasses-kafka.md) | Interactive search does not go through Kafka | runtime | Accepted |
| [0008](0008-coverage-before-price.md) | Rank on coverage before price | planner | Accepted |
| [0009](0009-freshness-gates-warmth.md) | Available is not acceptable: freshness gates warmth | cache | Accepted |
| [0010](0010-test-key-mode-precedence.md) | A test key overrides the execution mode, absolutely | execution | Accepted |
| [0011](0011-rls-plus-application-guards.md) | Tenant isolation enforced twice | tenancy | Accepted |
| [0012](0012-append-only-audit-log.md) | The audit log is append-only in the database | governance | Accepted |
| [0013](0013-explicit-event-loop-factory.md) | Run uvicorn through an explicit loop factory | runtime | Accepted |
| [0014](0014-persist-every-candidate.md) | Persist every candidate plan, not just the winner | planner | Accepted |

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

## Writing a new one

- **Copy the shape above**, number it next in sequence, and add it to the table
- Add it to the reading order with `make docs-nav`, which regenerates every page's header and previous/next links

## Related

- [Architecture overview](../architecture/overview.md)
- [Product overview](../product/product-overview.md)
- [Documentation index](../README.md)
- [Project README](../../README.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Troubleshooting](../operations/troubleshooting.md) | [Docs index](../README.md) | [ADR 0001: Rank candidate plans on marginal cost, n…](../adr/0001-marginal-cost-replanning.md) |
