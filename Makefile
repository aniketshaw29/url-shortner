.PHONY: setup redis-up redis-down db-init db-reset run test lint fmt smoke clean

setup:
	uv sync
	test -f .env || cp .env.example .env
	mkdir -p data
	uv run alembic upgrade head

redis-up:
	@if command -v brew >/dev/null 2>&1; then \
		brew services start redis; \
	else \
		docker compose up -d redis; \
	fi

redis-down:
	@if command -v brew >/dev/null 2>&1; then \
		brew services stop redis; \
	else \
		docker compose stop redis; \
	fi

db-init:
	uv run alembic upgrade head

db-reset:
	rm -f data/app.db data/app.db-wal data/app.db-shm
	uv run alembic upgrade head

run:
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check app tests migrations
	uv run mypy app

fmt:
	uv run ruff format app tests migrations
	uv run ruff check --fix app tests migrations

smoke:
	bash scripts/smoke.sh

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
