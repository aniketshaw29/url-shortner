# ADR-0001: Key Generation Strategy

- Status: accepted
- Date: 2026-11-04
- Deciders: project owner

## Context

Every link needs a short, unique code. The redirect path knows only the code, so lookup must be a single point read. Tier 1 creates ~1M links/month; Tier 2 is 100× that. Codes should not be trivially enumerable because enumeration leaks private links.

Seven base62 characters provide `62^7 ≈ 3.5 trillion` values.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| DB sequence → base62 | No collisions; simple | Enumerable; writes depend on ID generation; leaks volume |
| Random 7-char + unique index retry | No coordination; unguessable; even distribution | Rare retries; needs conflict handling |
| Hash(long URL) | Deterministic dedupe | Collisions; no clean TTL/custom alias; leaks URL equality |
| Snowflake / range allocator | Sortable; shard-friendly; no per-write coordination | Extra component; still enumerable; clock concerns |

## Decision

Generate 7 random base62 characters per link and rely on the unique index on `links.code` to arbitrate. On conflict, regenerate up to 5 times, then return `500`. Custom aliases use the same constraint but return `409` on conflict.

Expected collisions:

- Tier 1 (1M links): `N²/(2·62^7) ≈ 0.14` total over the dataset.
- Tier 2 (100M links): `≈ 1,400` total, or `≈ 1.4×10⁻⁵` per insert.

Regeneration is cheaper than coordination at both tiers.

## Consequences

- No ID service on the write path; sharding by `hash(code)` distributes evenly.
- Conflict handling is mandatory in the create path and must be tested under concurrency.
- Codes are case-sensitive; custom aliases are normalized to lowercase.
- Reserved/offensive codes require a blocklist check before insert.
- Deleted codes are not reused immediately (30-day tombstone).

## Revisit triggers

- Retry rate >0.1% or write p99 >100ms due to contention.
- Need for time-sortable codes or per-owner sequences.
- Code length becomes a product requirement.
- Tier 2 requires shard-local ID generation with no cross-shard coordination.
