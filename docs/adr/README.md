# Architecture decision records

The decisions that were not obvious, with the reasoning that produced them and
the thing that was given up.

An ADR is here when the alternative was genuinely defensible. "We used
PostgreSQL" is not a decision record; "we rank on coverage before price, which
means a cheaper plan can lose" is.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-marginal-cost-replanning.md) | Rank candidate plans on marginal cost, not cold cost | Accepted |
| [0002](0002-typed-catalog-edges.md) | Two separate edge sets: dependency and substitute | Accepted |
| [0003](0003-deterministic-semantic-guard.md) | A deterministic guard independent of the cosine score | Accepted |
| [0004](0004-hmac-for-api-keys.md) | HMAC-SHA256 for API keys, Argon2id for passwords | Accepted |
| [0005](0005-envelope-encryption.md) | Envelope encryption for upstream credentials | Accepted |
| [0006](0006-no-credential-field-in-schemas.md) | The credential field is absent from schemas, not excluded | Accepted |
| [0007](0007-interactive-search-bypasses-kafka.md) | Interactive search does not go through Kafka | Accepted |
| [0008](0008-coverage-before-price.md) | Rank on coverage before price | Accepted |
| [0009](0009-freshness-gates-warmth.md) | Available is not acceptable: freshness gates warmth | Accepted |
| [0010](0010-test-key-mode-precedence.md) | A test key overrides the execution mode, absolutely | Accepted |
| [0011](0011-rls-plus-application-guards.md) | Tenant isolation enforced twice | Accepted |
| [0012](0012-append-only-audit-log.md) | The audit log is append-only in the database | Accepted |
| [0013](0013-explicit-event-loop-factory.md) | Run uvicorn through an explicit loop factory | Accepted |
| [0014](0014-persist-every-candidate.md) | Persist every candidate plan, not just the winner | Accepted |

## Format

Each record states the context, the decision, the alternatives that were
rejected and why, and the cost of the choice. The cost section is not
decoration: a decision with no downside was not a decision.

## Related

- [Architecture overview](../architecture/overview.md)
- [Product overview](../product/product-overview.md)
- [Documentation index](../README.md)
- [Project README](../../README.md)

---

<div align="center">
<sub>&copy; 2026 SerpFlow. All rights reserved.</sub>
</div>
