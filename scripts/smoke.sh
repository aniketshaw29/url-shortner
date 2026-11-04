#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-dev-api-key}"
LONG_URL="${1:-https://example.com/}"

echo "health: $(curl -fsS "$BASE_URL/healthz")"

RESPONSE="$(curl -fsS -X POST "$BASE_URL/api/v1/links" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"long_url\":\"$LONG_URL\"}")"
echo "created: $RESPONSE"

CODE="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["code"])' "$RESPONSE")"
echo "redirect: $(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' "$BASE_URL/$CODE")"

STATS="$(curl -fsS "$BASE_URL/api/v1/links/$CODE/stats" \
  -H "Authorization: Bearer $API_KEY")"
echo "stats: $STATS"
