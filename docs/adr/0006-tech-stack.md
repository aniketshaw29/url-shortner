# ADR-0006: Language, Framework, and Tooling

- Status: accepted
- Date: 2026-11-04
- Deciders: project owner

## Context

The stack should make system-design concepts visible (HTTP, SQL, caching, concurrency) without hiding them behind heavy frameworks. It must support fast tests, containerized dependencies, and easy load testing. Python + SQLite was chosen as the learning stack.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Python + FastAPI + SQLAlchemy | Readable; explicit HTTP; strong typing with Pydantic; fast iteration | Lower raw throughput than Go; GIL limits CPU-bound work |
| Python + Django | Batteries included; admin UI | More framework magic; heavier for a small API |
| Go + chi + pgx | High throughput; explicit concurrency | More boilerplate; slower iteration for this learner |
| TypeScript + Fastify | Shared types; large ecosystem | Runtime/dependency overhead |

## Decision

- **Language:** Python 3.12+ managed with `uv`
- **API:** FastAPI + Uvicorn (2 workers in production)
- **DB:** SQLite 3.38+ (WAL) via SQLAlchemy 2.0 + Alembic (`render_as_batch=True`)
- **Cache/queue:** Redis 7 (cache, rate limits, click stream)
- **Config:** pydantic-settings + environment variables
- **Tests:** pytest, pytest-asyncio, httpx, fakeredis or a Redis container
- **Quality:** ruff (format + lint), mypy
- **Load:** k6
- **Packaging/deploy:** multi-stage Docker image, Docker Compose, Caddy, Litestream

Sync SQLAlchemy sessions are used with short scopes; FastAPI runs sync endpoints in a threadpool. Async is reserved for I/O-heavy paths if measurements justify it.

## Consequences

- The API contract and data model remain stack-agnostic.
- Throughput headroom is sufficient for Tier 1 (200 RPS peak); Tier 2 would likely use Go or multiple app nodes.
- SQLite keeps local development dependency-free (Redis is optional for unit tests via fakeredis).
- Python packaging and type checking are enforced in CI to offset dynamic-language risks.

## Revisit triggers

- Tier 1 load target cannot be met without disproportionate optimization.
- CPU-bound work (e.g., analytics) dominates and needs a different runtime.
- Team preference changes before Phase 1 starts.
