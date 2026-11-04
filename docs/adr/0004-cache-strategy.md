# ADR-0004: Redis Cache-Aside Strategy

- Status: accepted
- Date: 2026-11-04
- Deciders: project owner

## Context

Redirects outnumber writes ~100:1. SQLite can serve point reads quickly, but the cache keeps read load and latency predictable during traffic spikes and prevents WAL/read contention. Most traffic concentrates on a small set of links.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| No cache | Always fresh; simplest | SQLite and CPU absorb full read volume; spikes hurt |
| Cache-aside (lazy) | Simple, resilient, only hot data cached | Cold-start misses; invalidation logic |
| Write-through | Fresh cache | Writes pay double cost; caches cold links |
| In-process TTL cache only | No extra service | Per-worker duplication; lost on restart; hard to invalidate |

## Decision

Use Redis cache-aside for `code → link metadata` with:

- TTL 1 hour + random jitter.
- Negative caching for misses (30–60s).
- Delete-on-write invalidation for deactivation.
- Expiry enforced from the cached value on every read.
- Per-key single-flight fills to prevent stampedes.
- Redis persistence disabled; it is disposable.

Cache failures degrade to SQLite rather than failing the request. A small in-process TTL cache may be added later for the hottest keys.

## Consequences

- Cache hit ratio is the primary operational metric (target >95%).
- A stale entry cannot outlive `expires_at` because expiry is checked at read time.
- Cache and DB must agree on status transitions; tests cover delete/expire races.
- Redis is a latency dependency but not a correctness dependency.
- Rate-limit counters reset on Redis restart; acceptable at Tier 1.

## Revisit triggers

- Hit ratio <90% after warm-up.
- Redis cost or eviction pressure exceeds budget.
- Multi-region requires local caches or edge caching.
- Per-key hotspots saturate a Redis shard.
