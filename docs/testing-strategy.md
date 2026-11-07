# Testing Strategy

## Goals

- Prove the redirect contract, not just happy paths.
- Catch uniqueness, expiry, and SQLite concurrency bugs before production.
- Tie performance and durability claims to repeatable load and restore drills.

## Test pyramid

| Layer | Scope | Tooling | Speed |
| --- | --- | --- | --- |
| Unit | Base62, validation, expiry, rate-limit math | pytest | ms |
| Integration | API + SQLite + Redis | pytest, httpx, temporary DB, fakeredis or container Redis | seconds |
| Contract | Requests/responses match `api-spec.md` | pytest + schema assertions | seconds |
| E2E | Create → redirect → stats | httpx against a running app | seconds |
| Load | Redirect and create paths | k6 | minutes |
| Ops drills | Backup/restore, rollback, Redis loss | scripts + staging | minutes |

## Must-have test cases

### Unit

- Base62 encode/decode round-trip; length and alphabet.
- URL validation: schemes, length, credentials, unicode/punycode, private IPs.
- Alias rules: length, charset, reserved words, case folding.
- Expiry boundary: `expires_at == now` is expired.
- Rate-limit fixed-window math and window reset.

### Integration (SQLite-specific)

- Concurrent creates never produce duplicate codes; `UNIQUE` conflicts are retried and eventually surface as `500`.
- Custom alias conflict returns `409`, not `500`.
- Expired link returns `410`; deleted link returns `410`; unknown returns `404`.
- Cache invalidation on delete; a stale cache entry cannot resurrect a link.
- Rate limiter returns `429` with `RateLimit-*` and `Retry-After` headers.
- WAL + `busy_timeout`: parallel writers wait and succeed rather than returning `SQLITE_BUSY`.
- A long-running read does not block writes (WAL behavior); WAL size returns to normal after checkpoints.
- Migrations run on both an empty DB and a copy of a production-like DB (with data).
- `PRAGMA foreign_keys` is enabled per connection (delete an owner and assert `SET NULL`/`CASCADE` behavior).

### Contract

- Error responses always match `{error: {code, message, request_id}}`.
- `Location` header is a valid absolute URL and rejects header injection payloads.
- Redirect responses include `Cache-Control: no-store`.

### E2E

- Create with alias → redirect → stats reflect one click (allow the expected async delay).
- Idempotency-Key replay returns the same resource and does not create a second row.
- Pagination cursor is stable under concurrent inserts.

### Load (k6)

| Scenario | Profile | Pass criteria |
| --- | --- | --- |
| Redirect warm cache | 200 RPS, 15 min | p99 <100ms, error <0.1% |
| Redirect cold cache | 200 RPS, 5 min after cache flush | p99 <250ms, no write failures |
| Create burst | 10 RPS, 10 min | p99 <100ms, no duplicate codes, no `SQLITE_BUSY` |
| Mixed | 100:1 read/write for 15 min | SLOs hold, WAL size bounded |
| 2× peak | 400 RPS redirects | graceful degradation; alerts fire correctly |

Start load tests against staging, not production. Record results in the learning log.

### Failure and ops drills

- Redis unavailable → redirects still work via SQLite; latency within the breach budget.
- API restart under load → Caddy serves a short 502/maintenance window; health checks recover.
- Litestream stopped for 10 minutes → alert fires; replication resumes and catches up.
- Restore from object storage to a clean host → known codes resolve; click totals match the snapshot.
- Rollback to the previous image tag → app works with the current schema (backward-compatible migration).
- Disk-full simulation (small tmpfs or quota) → alert fires; runbook steps recover service.

## Non-functional checks

- Security: SSRF payloads, `javascript:`/`data:` URLs, oversized inputs, header injection, alias enumeration rate limits.
- Privacy: no raw IPs in logs or storage; retention job verified; IP hash salt not logged.
- Backpressure: click event queue is bounded; drop counter increments under overload.
- Time: all stored timestamps are UTC; API serialization is RFC 3339.

## CI gates

1. `uv sync --frozen`
2. `ruff format --check` and `ruff check`
3. `mypy`
4. `pytest` (unit + integration; temporary SQLite; fakeredis or service container)
5. Alembic upgrade on an empty DB and a seeded DB
6. Docker build (multi-stage, non-root)
7. Optional nightly: k6 smoke, `pip-audit`, image scan

## Coverage guidance

Aim for high coverage on encoding, validation, expiry, and the redirect contract. Do not chase 100% on glue code or configuration. Every production bug gets a regression test.

## Test data rules

- Use synthetic URLs; never real customer data.
- Generate codes deterministically only in unit tests; integration tests should use random codes plus explicit collision injection.
- Reset Redis between integration tests or use a unique key prefix per test.
- Run integration tests against a fresh SQLite file per test session; migration tests use a separate seeded fixture.
