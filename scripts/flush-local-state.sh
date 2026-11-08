#!/usr/bin/env bash
set -euo pipefail

redis_url="${REDIS_URL:-redis://localhost:6379/0}"

if ! command -v redis-cli >/dev/null 2>&1; then
  echo "redis-cli not found; skipping Redis cleanup" >&2
  exit 0
fi

for pattern in 'link:*' 'ratelimit:*' 'uv:*'; do
  redis-cli -u "$redis_url" --scan --pattern "$pattern" |
    xargs -n 500 redis-cli -u "$redis_url" unlink >/dev/null 2>&1 || true
done

redis-cli -u "$redis_url" unlink events:clicks >/dev/null 2>&1 || true
