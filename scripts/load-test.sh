#!/usr/bin/env bash
set -euo pipefail

base_url="${BASE_URL:-http://127.0.0.1:8000}"
api_key="${API_KEY:-dev-api-key}"

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is required: brew install k6" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi

echo "note: use 'make run-load' for a 200 RPS benchmark; the default 600/min redirect limit will return 429"

created=$(curl -fsS -X POST "$base_url/api/v1/links" \
  -H "Authorization: Bearer $api_key" \
  -H "Content-Type: application/json" \
  -d '{"long_url":"https://example.com/load-test"}')
code=$(printf '%s' "$created" | jq -r '.code')
echo "load target: $code"

curl -fsS -o /dev/null "$base_url/$code"

CODE="$code" BASE_URL="$base_url" k6 run scripts/load-test.js

sleep 1
curl -fsS "$base_url/api/v1/links/$code/stats" \
  -H "Authorization: Bearer $api_key" | jq '{total_clicks, unique_visitors}'

if command -v redis-cli >/dev/null 2>&1; then
  redis_url="${REDIS_URL:-redis://localhost:6379/0}"
  redis-cli -u "$redis_url" --scan --pattern 'ratelimit:redirect:*' | while IFS= read -r key; do
    redis-cli -u "$redis_url" del "$key" >/dev/null
  done
fi
