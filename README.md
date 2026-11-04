# URL Shortener

A URL shortener built as a hands-on system design learning project. The goal is to ship a working redirector *and* evolve it through the stages a production system goes through: naive v1, caching, durability, analytics, and a production-like deployment.

## Status

Local v1 is running: create, redirect, cache-aside, rate limits, analytics worker, and stats. Deployment artifacts (Dockerfile, CI/CD, Litestream) are still Phase 4 work.

## Stack

- **Language:** Python 3.12+ with `uv`
- **API:** FastAPI + Uvicorn
- **Database:** SQLite (WAL mode) via SQLAlchemy 2.0 + Alembic
- **Cache / rate limits:** Redis 7
- **Deployment:** single Linux VPS, Docker Compose, Caddy (TLS), Litestream backups
- **Quality:** pytest, ruff, mypy, k6

## Documentation

| Doc | Purpose |
| --- | --- |
| [Requirements](docs/requirements.md) | Scope, SLOs, capacity estimates (Tier 1 + 100× design exercise) |
| [System Design](docs/system-design.md) | Architecture, read/write paths, caching, scaling, tradeoffs |
| [API Spec](docs/api-spec.md) | Endpoints, payloads, status codes, errors |
| [Data Model](docs/data-model.md) | SQLite schema, pragmas, indexes, retention, migrations |
| [Development Plan](docs/development-plan.md) | Phased roadmap with tasks and exit criteria |
| [Deployment Plan](docs/deployment.md) | Production-like single-VPS topology, CI/CD, backups, runbooks |
| [Testing Strategy](docs/testing-strategy.md) | Test pyramid, load tests, failure injection |
| [Learning Log](docs/learning-log.md) | Journal of decisions and measurements |
| [ADRs](docs/adr/README.md) | Architecture decision records |

## Design at a glance

- **Create:** `POST /api/v1/links` → 7-char base62 code stored in SQLite
- **Redirect:** `GET /{code}` → `302` with `Location`; served from Redis when warm
- **Durability:** SQLite WAL + continuous Litestream replication to object storage
- **Analytics:** asynchronous events → daily rollups; raw clicks retained briefly
- **Evolution:** single node → managed Postgres → replicas → sharding → edge (Tier 2 design exercise)

## Learning goals

1. Turn requirements into capacity estimates and SLOs.
2. Defend tradeoffs (SQLite vs Postgres, 301 vs 302, random vs counter codes).
3. Measure before optimizing (cache hit ratio, p99, DB QPS, queue lag).
4. Operate what you build (deploys, backups, restores, failure drills).

## Local development

Prerequisites: Python 3.12+, `uv`, and Redis (Homebrew or Docker).

```bash
make setup       # install deps, create .env, migrate SQLite
make redis-up    # brew services start redis (falls back to Docker Compose)
make run         # http://localhost:8000
```

In a second terminal:

```bash
make smoke
# or create a link manually:
curl -X POST http://localhost:8000/api/v1/links \
  -H 'Authorization: Bearer dev-api-key' \
  -H 'Content-Type: application/json' \
  -d '{"long_url":"https://example.com"}'
```

Local resources:

- SQLite: `data/app.db` (WAL mode)
- Redis: `localhost:6379`
- API key: `dev-api-key` from `.env`
- Analytics: click events flow through the `events:clicks` Redis Stream

Useful commands: `make test`, `make lint`, `make fmt`, `make db-reset`.

## Deployment summary

One 2 vCPU / 4 GB VPS running Docker Compose:
Caddy → FastAPI (2 workers) → SQLite on local SSD, with Redis for cache and
Litestream replicating the database to S3-compatible object storage.

Estimated cost: ~$6–10/month. See [Deployment Plan](docs/deployment.md).
