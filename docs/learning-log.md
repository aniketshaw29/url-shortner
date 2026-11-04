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
