# ADR-0005: Analytics Pipeline

- Status: accepted (provisional — revisit in Phase 5)
- Date: 2026-11-04
- Deciders: project owner

## Context

At Tier 1 (~100M redirects/month, ~40/s average) synchronous click inserts would add write load and couple the redirect path to analytics availability. At Tier 2 (10B/month) synchronous inserts are impossible. We need per-link totals, time series, referrers, and approximate unique visitors.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Synchronous insert | Simple, immediate | Couples latency/availability to analytics; write amplification |
| Redis Stream → worker → SQLite rollups | Decoupled; reuses SQLite; cheap | SQLite storage limits; stream trimming needed |
| Redis Stream → worker → ClickHouse | Columnar compression; fast aggregates | New operational component |
| Managed warehouse (BigQuery) | Low ops; scalable | Cost; query latency; vendor coupling |

## Decision

Tier 1: the redirect path appends a bounded event to a Redis Stream (non-blocking, with an in-process buffer fallback). A worker batches events into `clicks` (raw, ≤7 days) and idempotently updates `link_daily_stats` plus per-referrer daily counters. Unique visitors use HyperLogLog. Redirect latency must be unaffected by worker availability.

Tier 2: move raw events to a columnar store (ClickHouse preferred for learning; BigQuery acceptable managed alternative) and keep daily aggregates as the serving layer.

## Consequences

- Analytics has eventual consistency (target lag <5 minutes).
- The stream is bounded; overload drops events and increments a counter rather than blocking redirects.
- Rollup writes are batched and run off-peak to avoid SQLite write contention.
- Raw click retention is short because SQLite is not a columnar store.
- Replays are safe because rollups are idempotent.

## Open questions

- Sampling rate if event volume exceeds budget (e.g., 10%).
- HLL implementation: Redis HLL vs application-side sketch vs ClickHouse aggregate.
- Retention: 7 days raw / 13 months rollups at Tier 1.

## Revisit triggers

- Stream lag >5 minutes sustained.
- Analytics storage cost or DB size >20% of the total budget.
- Need for real-time dashboards.
- Tier 2 migration to Postgres/ClickHouse.
