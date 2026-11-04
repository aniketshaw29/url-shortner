# ADR-0002: SQLite as the Tier 1 Source of Truth

- Status: accepted
- Date: 2026-11-04
- Deciders: project owner

## Context

Links are small records with one hard invariant: codes are globally unique. The hot path is a point read by code, and created links must be durable. Tier 1 peaks at ~2 writes/s and ~200 reads/s, with reads served cache-first. Tier 2 (100×) is a design exercise, not a v1 requirement.

The project is also a systems-learning exercise: operating SQLite well (WAL, checkpoints, backups, restore) teaches fundamentals that a managed database can hide.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| SQLite (WAL) | No network hop; simple ops; fast reads; easy local dev; Litestream backups | Single writer; manual scaling; no built-in HA |
| PostgreSQL | Strong concurrency, replicas, extensions | More ops; managed cost; unnecessary at Tier 1 |
| MySQL | Similar to Postgres | Weaker fit for JSON/modern tooling here |
| DynamoDB/Cassandra | Horizontal scale | Conditional writes for uniqueness; more moving parts |

## Decision

SQLite is the source of truth for links, API keys, and analytics rollups at Tier 1. Use:

- WAL mode, `busy_timeout=5000`, short transactions
- A local SSD bind mount (never a network filesystem)
- Litestream continuous replication to S3-compatible object storage
- Nightly snapshots plus a monthly restore drill
- SQLAlchemy with portable SQL so the Postgres move stays mechanical

Redis handles caching and rate limits; it is never a correctness dependency.

## Consequences

- Uniqueness is enforced by the database, so retry handling is simple.
- Writes are serialized; this is acceptable at ~2/s peak but must be monitored.
- A single host is a single point of failure; RTO is restore time, not failover time.
- Long-running readers can delay WAL checkpoints; analytics jobs must be batched and monitored.
- Migrations need Alembic batch mode and a pre-migration backup.

## Revisit triggers

Move to Postgres when any of these hold for a week:

- Sustained writes >50/s or `SQLITE_BUSY` retries >1%
- DB >20GB or restore >1 hour
- p99 >150ms with a warm cache and exhausted CPU headroom
- Availability requirement >99.5% or zero-downtime deploys required
- Multi-region or read-replica requirement appears

See [deployment.md](../deployment.md#17-scaling-triggers) for the operational thresholds.
