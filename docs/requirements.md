# Requirements

## 1. Purpose

Define what the URL shortener must do, how well it must do it, and what is out of scope. These requirements drive the [system design](system-design.md), [development plan](development-plan.md), and [deployment plan](deployment.md).

## 2. Users and use cases

| Actor | Use case |
| --- | --- |
| Anonymous visitor | Follow a short link |
| Registered user | Create, manage, and inspect links |
| API client | Programmatic creation and stats |
| Operator | Deploy, monitor, rate-limit, investigate abuse |

v1 uses API keys rather than full user accounts; the schema leaves room for owners.

## 3. Functional requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-1 | Create a short link from an absolute `http`/`https` URL | Must |
| FR-2 | Redirect `GET /{code}` to the original URL | Must |
| FR-3 | Generate a unique code automatically | Must |
| FR-4 | Accept a custom alias when available | Should |
| FR-5 | Expire links at an optional `expires_at` | Should |
| FR-6 | Deactivate/delete a link | Should |
| FR-7 | Return basic click counts per link | Should |
| FR-8 | Return time-series and referrer/device breakdowns | Could |
| FR-9 | List a user's links with pagination | Could |
| FR-10 | Reserve aliases and block offensive codes | Must (safety) |

### Acceptance rules

- Long URLs must be absolute `http`/`https`; reject `javascript:`, `data:`, `file:`, and credentialed URLs.
- Generated codes are 7 characters from `[0-9A-Za-z]`; custom aliases are 3–30 characters from `[a-z0-9_-]` (case-insensitive uniqueness).
- Expired, deleted, or blocked links never redirect.
- Creating the same long URL twice may produce two codes; idempotency is opt-in via header.
- Redirect responses must not be cached by browsers in v1 (`Cache-Control: no-store`).

## 4. Scale tiers

The implementation targets **Tier 1** on a single VPS. **Tier 2** is a design exercise: the same product at 100× volume, used in later phases to reason about Postgres, replicas, sharding, and columnar analytics.

| Metric | Tier 1 (v1 deployed) | Tier 2 (design exercise) |
| --- | --- | --- |
| New links / month | 1,000,000 | 100,000,000 |
| Redirects / month | 100,000,000 | 10,000,000,000 |
| Avg writes | ~0.4/s | ~40/s |
| Peak writes (5×) | ~2/s | ~200/s |
| Avg reads | ~40/s | ~3,900/s |
| Peak reads (5×) | ~200/s | ~19,000/s |
| Link storage / month | ~500MB | ~50GB |
| Raw clicks / month | ~10GB | ~1TB |

Assumptions: 30-day month ≈ 2.6M seconds; ~500B per link row including index; ~100B per click event.

## 5. Non-functional requirements

| ID | Requirement | Tier 1 target |
| --- | --- | --- |
| NFR-1 | Redirect latency | p50 < 10ms, p99 < 100ms server-side |
| NFR-2 | Create latency | p99 < 100ms |
| NFR-3 | Availability | 99.5% monthly (single node, planned maintenance excluded) |
| NFR-4 | Durability | No acknowledged link lost; RPO < 10s, RTO < 30min |
| NFR-5 | Read/write ratio | Support 100:1 |
| NFR-6 | Concurrency | 200 redirects/s at 5× peak with cache warm |
| NFR-7 | Security | Rate limiting, URL validation, abuse blocklist |
| NFR-8 | Privacy | Store salted IP hashes only; raw click retention ≤ 7 days |
| NFR-9 | Observability | RED metrics, structured logs, request IDs, alerting |

Tier 2 targets (99.9% availability, p99 < 50ms at ~19K RPS) are discussed in the system design but are not implemented in v1.

## 6. Capacity implications for SQLite

At Tier 1 the write load (~2/s peak) is far below SQLite's single-writer limit, and hot reads are served from Redis. The design is viable on one node with:

- WAL mode, `busy_timeout`, and short write transactions
- Redis cache-aside to keep read load off SQLite
- Raw click retention of ≤7 days plus daily rollups
- Continuous replication via Litestream for durability

At Tier 2, SQLite is not appropriate: writes, dataset size, and availability requirements force a move to Postgres (see [ADR-0002](adr/0002-primary-datastore.md)).

## 7. Out of scope (v1)

- Full user accounts, teams, billing
- Multi-region or active-active
- Custom domains (stretch)
- Real-time analytics (<1 minute freshness)
- ML-based abuse detection
- Public analytics dashboards

## 8. Open questions

- Anonymous link creation: allowed with stricter rate limits, or API key required?
- Analytics retention: 7 days raw / 13 months rollups proposed.
- Custom domains: Phase 6 stretch or drop?
