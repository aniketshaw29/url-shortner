# Architecture Decision Records

ADRs capture decisions that are expensive to reverse. Format: context → options → decision → consequences. Status values: proposed, accepted, superseded, rejected, deferred.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-key-generation-strategy.md) | Random base62 codes with unique-index retry | Accepted |
| [0002](0002-primary-datastore.md) | SQLite as the Tier 1 source of truth | Accepted |
| [0003](0003-redirect-status-and-caching.md) | `302` redirects, `no-store` in v1 | Accepted |
| [0004](0004-cache-strategy.md) | Redis cache-aside with negative caching | Accepted |
| [0005](0005-analytics-pipeline.md) | Async events → rollups → columnar store at Tier 2 | Accepted (provisional) |
| [0006](0006-tech-stack.md) | Python + FastAPI + SQLite + Redis | Accepted |
| [0007](0007-deployment-topology.md) | Single VPS with Docker Compose + Litestream | Accepted |

## Template

```markdown
# ADR-NNNN: Title

- Status: proposed | accepted | rejected | superseded by ADR-XXXX | deferred
- Date: YYYY-MM-DD
- Deciders: names/roles

## Context

Forces at play, constraints, and the requirement that triggers the decision.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A | | |
| B | | |

## Decision

What we chose.

## Consequences

Positive, negative, and follow-up work.

## Revisit triggers

Metrics or conditions that would reopen this decision.
```
