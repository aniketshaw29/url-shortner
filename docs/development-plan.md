# Development Plan

## Principles

1. Every phase ends with something deployable and measured.
2. Introduce a concept only when a metric or requirement demands it.
3. Write the decision down (ADR) before the code.
4. Measure before and after each optimization; keep numbers in the learning log.
5. The deployment path is exercised early, not bolted on at the end.

## Phase overview

| Phase | Theme | Key concepts | Exit criteria |
| --- | --- | --- | --- |
| 0 | Docs and decisions | Requirements, estimates, ADRs | Docs reviewed; stack decided |
| 1 | Walking skeleton | FastAPI, SQLite, base62, tests, CI | Create + redirect work end to end |
| 2 | Product completeness | Aliases, expiry, deletion, stats, rate limits | All Must/Should FRs pass acceptance tests |
| 3 | Read performance | Redis cache-aside, load testing | p99 <100ms at 200 RPS, hit ratio >95% |
| 4 | Durability + deploy | Docker, Caddy, Litestream, CI/CD, drills | Staging deploy, restore drill, rollback drill pass |
| 5 | Analytics pipeline | Redis Streams, batching, rollups, HLL | Stats lag <5min; redirect p99 unchanged |
| 6 | Production readiness | SLOs, tracing, security, game day | Go-live checklist complete; game day passes |

Time-box: 1–2 weeks per phase part-time. Do not skip exit criteria.

## Proposed repository layout

```text
app/
  main.py              # FastAPI app factory, lifespan, health endpoints
  api/                 # routers: links, redirect, stats
  core/                # config, security, logging, rate limiting
  db/                  # SQLAlchemy models, session, pragmas
  services/            # link creation, expiry, analytics
  workers/             # click event consumer, cleanup job
tests/
  unit/
  integration/
  e2e/
migrations/            # Alembic
deploy/                # Caddyfile, compose.yml, litestream.yml
load/                  # k6 scripts
docs/
```

Tooling: `uv`, ruff (format + lint), mypy, pytest, pytest-asyncio, httpx, Alembic, k6.

## Phase 0 — Docs and decisions

- [x] Requirements and capacity estimates
- [x] System design and tradeoffs
- [x] API spec and data model
- [x] Testing strategy
- [x] Deployment plan
- [x] ADR-0001 key generation
- [x] ADR-0002 SQLite as primary datastore
- [x] ADR-0003 redirect semantics
- [x] ADR-0004 cache strategy
- [x] ADR-0005 analytics pipeline (provisional)
- [x] ADR-0006 Python/FastAPI/SQLite stack
- [x] ADR-0007 single-VPS deployment topology
- [ ] Review docs and resolve open questions in `requirements.md`

Exit: no unresolved blocking questions; Phase 1 can start.

## Phase 1 — Walking skeleton

Goal: the thinnest end-to-end slice, deployed to staging.

- [x] `uv init`; add FastAPI, Uvicorn, SQLAlchemy, Alembic, pydantic-settings, Redis client
- [x] Config via env vars; `.env.example`; no secrets in git
- [x] App factory + lifespan; `/healthz` (liveness) and `/readyz` (DB + Redis)
- [x] SQLAlchemy engine with SQLite pragmas; Alembic baseline migration
- [x] `POST /api/v1/links` with URL validation and random base62 code
- [x] `GET /{code}` redirect with `302`, expiry check, and `no-store`
- [x] Structured logging with request IDs
- [x] Unit tests for base62/validation; integration test for create → redirect
- [ ] CI: `ruff format --check`, `ruff check`, `mypy`, `pytest`, migration check, Docker build
- [ ] Dockerfile (multi-stage, non-root) + local `compose.yml`
- [ ] Deploy to a staging host early with a minimal Compose file (harden in Phase 4)

Concepts: HTTP semantics, unique constraints, collision retry, 12-factor config.
Exit: a newcomer can create and follow a link locally with one command; staging serves a redirect.

## Phase 2 — Product completeness

- [x] Custom aliases with reserved-word/offensive blocklist
- [x] `expires_at` validation and `410 Gone` behavior
- [x] `DELETE` (soft delete) and cache invalidation
- [x] `GET` metadata + basic total clicks
- [x] Rate limiting (Redis fixed-window counters) with standard headers
- [ ] API key auth (hashed keys, pepper) — local v1 uses an env key
- [x] Error taxonomy matching `api-spec.md`
- [ ] Acceptance test suite covering every FR
- [ ] Abuse guardrails: private-IP rejection, domain blocklist hook (scheme allowlist done)

Exit: all Must/Should requirements pass automated acceptance tests in CI.

## Phase 3 — Read performance

- [x] Redis cache-aside with jitter and negative caching
- [ ] Single-flight cache fill; stampede test
- [x] Metrics: cache hit ratio, redirect outcomes, HTTP p50/p99, error rate
- [ ] SQLite read and `SQLITE_BUSY` metrics
- [x] k6 warm-cache smoke: 200 RPS × 60s, p99 9.84ms, 0 errors
- [ ] k6 soak: 200 RPS × 15 minutes, mixed 100:1
- [x] Cold-cache baseline: 97.2% miss, p99 11.2ms
- [x] Before/after numbers in the learning log

Exit: p99 <100ms at 200 RPS; cache hit ratio >95%; no `SQLITE_BUSY` errors under load.

## Phase 4 — Durability and deployment

Goal: run it like a small production service.

- [ ] Production `Dockerfile` (pinned base image, non-root, healthcheck)
- [ ] `deploy/compose.yml`: Caddy, API, Redis, Litestream
- [ ] Caddy TLS + security headers; HTTPS verified
- [ ] SQLite on local SSD; pragmas applied on every connection
- [ ] Litestream continuous replication to object storage
- [ ] Nightly snapshot + documented restore procedure
- [ ] GitHub Actions: build/push image on tag; SSH deploy with health check and rollback
- [ ] Host hardening: UFW, SSH keys, fail2ban, unattended upgrades, swap
- [ ] Idempotent deploy script; backup before migration
- [x] Redis outage drill: 200 RPS, p99 2.29ms, 0 errors, analytics dropped
- [ ] Remaining failure drills: API restart, restore to a new host, rollback
- [ ] Uptime probe and basic alerts

Exit: staging deploy, restore drill, and rollback drill all pass; RPO <10s measured, RTO <30min measured.

## Phase 5 — Analytics pipeline

- [x] Publish click events to a bounded Redis Stream from the redirect path (non-blocking)
- [x] Worker consumes in batches; inserts raw `clicks` and updates `link_daily_stats`
- [x] Unique visitors via HyperLogLog
- [x] `GET /stats` backed by rollups, not raw scans
- [ ] Cleanup job: expired links, raw clicks >7 days, incremental vacuum
- [ ] Replay/backfill tool; idempotent aggregation
- [ ] Load test analytics at 10× Tier 1 click volume
- [ ] Update ADR-0005 with measured results

Exit: stats lag <5 minutes; redirect p99 unchanged; no analytics-related write contention.

## Phase 6 — Production readiness

- [ ] SLOs + dashboards (availability, latency, cache hit ratio, stream lag, disk, Litestream lag)
- [ ] Tracing across API → cache → SQLite → worker
- [ ] Alerting with runbooks (see `deployment.md`)
- [ ] Backup/restore and DNS failover drills on a clean host
- [ ] Security review: authz, SSRF, rate limits, secrets, dependency scan
- [ ] Load test at 2× Tier 1 peak (400 RPS) with Redis failure injection
- [ ] Game day: on-call runbook walkthrough
- [ ] Scaling decision: stay on SQLite or start the Postgres migration
- [ ] Optional stretch: CDN/edge redirects, custom domains, blue-green deploy

Exit: an on-call engineer can diagnose and mitigate each alert using only the docs.

## Milestones

| Milestone | Definition |
| --- | --- |
| M0 Docs | This document set reviewed; stack decided |
| M1 Demo | Create + redirect works locally and on staging |
| M2 v1 | All Must/Should FRs pass; deployed with HTTPS |
| M3 Fast | Cache + load test; SLO met at 200 RPS |
| M4 Durable | Litestream, CI/CD, restore and rollback drills pass |
| M5 Data | Analytics pipeline at target volume |
| M6 Production | Go-live checklist and game day complete |

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Scope creep before v1 | Freeze FR list; park ideas in a backlog |
| Premature optimization | Require a measured trigger per phase |
| SQLite write contention | Short transactions, batch jobs off-peak, `busy_timeout` alerting |
| Analytics slows redirects | Async-only; bounded queue with drop policy |
| Backups untested | Monthly restore drill; record RTO |
| Docs drift | Update docs/ADRs in the same PR as behavior changes |
| Single-node outage | Explicit tradeoff; restore runbook and off-site backups |

## Definition of done (every phase)

- Code merged with tests and docs updated
- Metrics/dashboards cover the new path
- ADR added/updated for non-trivial decisions
- Learning log entry with before/after measurements
- Demo script works from a clean environment
