# Learning Log

One entry per phase or significant decision. Keep it short and numeric.

## Template

```markdown
## YYYY-MM-DD — Phase N: <topic>

**Question:** What were we trying to learn or decide?

**Context:** Load, data size, or constraint that made this relevant.

**Options considered:** A / B / C with one-line tradeoffs.

**Decision:** What we chose and why.

**Measurement:** Before/after numbers (p99, QPS, hit ratio, cost).

**What surprised me:** The non-obvious part.

**Next question:** What this raises for the next phase.
```

## 001 — 2026-11-04 — Phase 0: Key generation

**Question:** Should short codes come from a counter or random generation?

**Context:** Tier 1 is 1M links/month; Tier 2 is 100M/month. Seven base62 chars give ~3.5T codes. The redirect path should not depend on a central ID service.

**Options considered:**

- DB sequence → base62: simplest, but enumerable and couples writes to the primary.
- Random 7-char + unique constraint: no coordination, unguessable; rare retries.
- Hash of URL: dedupes but collides and complicates expiry/custom aliases.

**Decision:** Random 7-char base62 with unique-index retry.

**Measurement:** Expected collisions at Tier 1 ≈ 0.14 total; at Tier 2 (100M links) ≈ 1,400 total, or ~1.4×10⁻⁵ per insert. To be verified with a concurrency test in Phase 1.

**What surprised me:** The retry rate is so low that coordination would be pure overhead.

**Next question:** At what write volume does a range allocator beat retry-on-insert?

## 002 — 2026-11-04 — Phase 0: SQLite as the primary datastore

**Question:** Can SQLite be the source of truth for a production-like deployment?

**Context:** Tier 1 peaks at ~2 writes/s and ~200 reads/s; reads are cache-first. The alternative is Postgres, which adds operational surface but handles Tier 2.

**Options considered:**

- SQLite + WAL: one writer, many readers, zero network hop, trivial backups with Litestream.
- Postgres: stronger concurrency, replicas, but more ops and a managed-service cost.
- Key-value store: fast point reads, weak fit for ownership/listing/stats.

**Decision:** SQLite for Tier 1; keep SQL portable and migrate to Postgres when the documented triggers are hit.

**Measurement:** To be validated in Phase 3: p99 at 200 RPS, `SQLITE_BUSY` rate, WAL size, DB growth (~500MB/month).

**What surprised me:** The hardest part is not reads or writes — it is durability discipline (WAL, checkpoints, backups, disk alerts).

**Next question:** What does restore time look like at 5GB, 20GB, and 50GB?

## 003 — 2026-11-04 — Phase 0: Single-VPS deployment topology

**Question:** What is the simplest deployment that still teaches production operations?

**Context:** The goal is to learn deploys, TLS, backups, monitoring, and rollback — not Kubernetes.

**Options considered:**

- PaaS (Fly.io/Render): least ops, but hides most of the learning.
- Single VPS + Docker Compose: explicit networking, TLS, volumes, backups; cheap.
- Kubernetes: realistic at scale, disproportionate for one service and one SQLite file.

**Decision:** One 2 vCPU / 4GB VPS, Caddy → FastAPI → SQLite, Redis, Litestream to object storage, GitHub Actions deploys.

**Measurement:** Target cost $6–10/month; RPO <10s; RTO <30min; deploy downtime 3–10s.

**What surprised me:** The deployment plan forces decisions (backup format, secret handling, rollback) that the application design alone does not.

**Next question:** Is blue-green with two API containers sharing SQLite worth the complexity, or is a 5-second maintenance window acceptable?

## 004 — 2026-11-04 — Phase 1: Local full-stack walking skeleton

**Question:** Does the documented Tier 1 design work end to end locally with real SQLite and Redis?

**Context:** Local macOS setup: Python 3.12, SQLite 3.50, Redis 8.10 via Homebrew. No Docker daemon at the time.

**Options considered:**

- Run everything in Docker Compose: portable, but requires the daemon.
- Run FastAPI natively + Redis via Homebrew + SQLite file: fastest local loop.
- Use fakeredis for everything: good for tests, not a real integration check.

**Decision:** Native app, real local Redis, SQLite file, and fakeredis only in unit/integration tests. Smoke script exercises the real stack.

**Measurement:** 17 tests pass. Smoke run: create 19.9ms, cold redirect 7.6ms, stats 6.2ms. The worker rolled up the click and HLL unique count within the same second; stats showed `total_clicks=1`, `unique_visitors=1`.

**What surprised me:** The Redis Stream + worker path was not visible in the redirect latency, and the first stats request already had data.

**Next question:** At 200 RPS, what do cache hit ratio, p99, and `SQLITE_BUSY` count look like?

## 005 — 2026-11-06 — Phase 3: First 200 RPS redirect baseline

**Question:** What is the warm-cache redirect limit on the local Tier 1 stack, and what breaks first?

**Context:** One Uvicorn worker, local SQLite WAL, local Redis, k6 `constant-arrival-rate` at 200 RPS for 60s, all traffic from one IP.

**Options considered:**

- Run against the default rate limit: measures the abuse control, not throughput.
- Raise only `RATE_LIMIT_REDIRECT_PER_MINUTE` for the benchmark: isolates redirect performance.
- Randomize `X-Forwarded-For`: would bypass the limiter but weakens the test.

**Decision:** Run both. First with defaults, then with `make run-load` and the redirect limiter raised to 1,000,000/minute.

**Measurement:**

- Default 600/minute per IP: 12,000 requests, 90% returned `429`; only 1,199 succeeded. This confirmed the limiter is active.
- Raised limiter: 12,001 requests, 200.16 RPS, 0 errors, p50 2.49ms, p95 3.55ms, p99 9.84ms, max 41.97ms.
- Analytics: 13,202 clicks rolled up, `unique_visitors=1`, no `500`s, no `SQLITE_BUSY`.
- Redis stats: 102,774 keyspace hits, 32 misses; these mix rate-limit and cache keys, so they are not a clean cache-hit ratio.

**What surprised me:** The rate limiter is the first bottleneck for a single-IP load test, not SQLite or Redis. The redirect path stayed under 10ms p99 once that was out of the way.

**Next question:** What does p99 look like with a cold cache and with Redis unavailable, and how do we measure cache hit ratio cleanly?

## 006 — 2026-11-07 — Cold-cache 200 RPS baseline

**Question:** How much does SQLite cost when nearly every redirect misses Redis?

**Context:** Seeded 200,000 active links directly into SQLite, flushed their cache, then sent 12,000 requests at 200 RPS for 60s from one IP with the redirect limiter raised.

**Measurement:** 11,665 unique codes were cached, so the run was ~97.2% cache miss / 2.8% hit. p50 2.82ms, p95 4.10ms, p99 11.20ms, max 115.41ms; 0 errors. All 12,000 clicks rolled up; no `500`s and no `SQLITE_BUSY`.

**What surprised me:** Cold-cache p99 was only ~1.4ms worse than warm. SQLite WAL reads at 200 RPS were not the bottleneck.

**Next question:** What happens when Redis disappears entirely?

## 007 — 2026-11-07 — Redis outage drill

**Question:** Do redirects survive Redis loss, and what is the latency and operational blast radius?

**Context:** Stopped local Redis while the API was running; 200 RPS for 30s from one IP with the redirect limiter raised.

**Options considered:**

- Fail closed: return `503` for redirects. Simple, but takes the product down for a disposable cache.
- Fail open to SQLite: keep redirects working, drop analytics, disable cache and rate limits.
- Keep retrying Redis per request: correct in theory, but the first drill showed a log storm and 477ms p99.

**Decision:** Fail open with a process-local circuit breaker: open for 5s after a Redis error, then allow one half-open probe; cache, rate-limit, and analytics calls skip Redis while open. `/readyz` still probes Redis and returns `503`.

**Measurement before the fix:** At 50 RPS for 10s, redirects returned `302` and p99 was 15.8ms, but traceback logging added ~92k log lines (~184 per request). A follow-up 200 RPS run without the breaker hit p99 477ms.

**Measurement after the fix:** At 200 RPS for 30s, 6,001 requests, 0 errors, p50 1.11ms, p95 1.67ms, p99 2.29ms, max 14.05ms. Only 11 warnings for the whole outage; `readyz` was `503`; service recovered to `200` after Redis restarted.

**Tradeoff:** Cache invalidation was skipped during an outage, so a link deleted then could remain in Redis until TTL after recovery. Click events during the outage are dropped; there is no persistent buffer.

**Next question:** Do we need cache generation/versioning or flush-on-recovery to prevent stale entries, and a durable buffer for analytics?

## 008 — 2026-11-08 — Cache invalidation recovery

**Question:** How do we stop a link deleted during a Redis outage from resurfacing after Redis returns?

**Options considered:**

- Cache generation/versioning: change the key namespace on recovery. Strong, but adds a generation lookup or per-worker namespace, and multi-worker sharing gets awkward.
- Flush every `link:*` key on recovery: simple and correct, but expensive with a large cache.
- Replay pending invalidations: remember codes deleted while Redis was unavailable; on recovery delete just those keys.

**Decision:** Queue invalidations in process while the circuit is open or a delete fails. On the first successful Redis call after recovery, flush the queued keys and force that cache read to fall through to SQLite. The request then re-caches the current database state.

**Tradeoff:** The pending set lives in process memory; a crash before replay can still leave stale keys until TTL. A shared cache-generation scheme would cover that, at the cost of more Redis coordination. Analytics events are still dropped during an outage.

**Test:** `test_deleted_link_does_not_resurrect_after_redis_recovery` deletes a cached link through a broken Redis client, restores Redis, and asserts the next redirect is `410`, not a stale `302`.

## 009 — 2026-11-08 — 15-minute soak

**Question:** Does 200 RPS stay healthy for 15 minutes, or do cache, SQLite, or the analytics worker degrade over time?

**Context:** One warmed link, one IP, redirect limit raised, 200 RPS × 15 minutes via k6.

**Measurement:** 180,000 requests, 0 failed, p50 1.8ms, p95 2.67ms, p99 6.09ms, max 133.01ms. Cache: 180,000 hits and 1 miss (100% after warm-up). Redirects: 180,001 `302`. Analytics stream trimmed at 100,006 entries, pending 0 at the end. `SQLITE_BUSY` 0. The worker kept up; SQLite grew to 21.3MB and 197,463 total raw clicks including earlier test data.

**Interpretation:** No latency drift, no error-rate drift, and no write contention under a steady warm read load. The p99 was lower than the 60s warm run, so the earlier `9.84ms` was not a floor. The analytics stream bound worked as intended: length stopped at 100k while pending stayed at 0.

**Next question:** What happens on API restart and on restore/rollback, and how do metrics behave with more than one Uvicorn worker?
