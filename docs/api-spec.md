# API Specification

Base URL: `https://s.example.com` (versioned JSON API under `/api/v1`; redirects at the root).

## Conventions

- JSON request/response with `Content-Type: application/json`.
- Timestamps are RFC 3339 UTC (`2026-11-04T12:00:00Z`).
- Authenticated endpoints use `Authorization: Bearer <api_key>`.
- Errors share one shape:

```json
{
  "error": {
    "code": "alias_taken",
    "message": "Custom alias is already in use",
    "request_id": "req_01J..."
  }
}
```

- Unknown fields are rejected with `400` to catch client mistakes early.

## Endpoints

### POST /api/v1/links

Create a short link.

Headers: `Authorization`, optional `Idempotency-Key`.

Request:

```json
{
  "long_url": "https://example.com/some/long/path?utm_source=newsletter",
  "custom_alias": "launch-2026",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `long_url` | string | yes | Absolute `http`/`https`, ≤2048 chars |
| `custom_alias` | string | no | 3–30 chars, `[a-z0-9_-]`, case-insensitive unique |
| `expires_at` | string | no | Future RFC 3339 timestamp |

Response `201 Created`:

```json
{
  "code": "aB3xY9z",
  "short_url": "https://s.example.com/aB3xY9z",
  "long_url": "https://example.com/some/long/path?utm_source=newsletter",
  "created_at": "2026-11-04T12:00:00Z",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

Errors: `400 invalid_url`, `409 alias_taken`, `422 alias_reserved`, `429 rate_limited`.

### GET /{code}

Redirect to the destination. Not JSON.

- `302 Found` with `Location` and `Cache-Control: no-store`.
- `404 not_found` for unknown codes.
- `410 gone` for expired, deleted, or blocked links.
- `429 rate_limited` when per-IP limits are exceeded.

### GET /api/v1/links/{code}

Return link metadata (owner only).

```json
{
  "code": "aB3xY9z",
  "long_url": "https://example.com/...",
  "created_at": "2026-11-04T12:00:00Z",
  "expires_at": null,
  "status": "active",
  "total_clicks": 1234
}
```

Errors: `401 unauthorized`, `403 forbidden`, `404 not_found`.

### DELETE /api/v1/links/{code}

Deactivate a link. Idempotent.

- `204 No Content` on success (including already deleted).
- `401`/`403`/`404` as above.

### GET /api/v1/links/{code}/stats

Query click analytics.

Query params: `from` (default 30 days ago), `to` (default now), `interval` (`day` in v1; `hour` is planned).

```json
{
  "code": "aB3xY9z",
  "range": {"from": "2026-10-05T00:00:00Z", "to": "2026-11-04T00:00:00Z"},
  "total_clicks": 1234,
  "unique_visitors": 987,
  "series": [
    {"bucket": "2026-11-03", "clicks": 120, "unique_visitors": 101}
  ],
  "top_referrers": [{"referrer": "news.ycombinator.com", "clicks": 300}]
}
```

`unique_visitors` is approximate (merged daily HyperLogLog sketches, ~2% error) and `top_referrers` comes from daily per-referrer rollups. Stats may lag live clicks by up to 5 minutes.

### GET /api/v1/links

List the caller's links, newest first.

Query params: `limit` (1–100, default 20), `cursor`, `status` (`active`|`expired`|`deleted`).

```json
{
  "items": [
    {"code": "aB3xY9z", "long_url": "https://example.com/...", "created_at": "2026-11-04T12:00:00Z", "total_clicks": 12}
  ],
  "next_cursor": "eyJpZCI6..."
}
```

## Rate limits

| Scope | Limit | Window |
| --- | --- | --- |
| Create per API key | 30 | 1 minute |
| Metadata/stats per API key | 300 | 1 minute |
| Redirect per IP | 600 | 1 minute |

Responses include `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`; `429` includes `Retry-After`.

## Error codes

| HTTP | Code | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Body/query validation failed |
| 400 | `invalid_url` | Malformed or unsupported URL |
| 400 | `invalid_alias` | Alias fails syntax rules |
| 400 | `invalid_expiry` | Expiry is not in the future |
| 400 | `invalid_range` | Stats range is inverted or too large |
| 400 | `invalid_cursor` | Pagination cursor is malformed |
| 401 | `unauthorized` | Missing/invalid API key |
| 403 | `forbidden` | Not the owner |
| 404 | `not_found` | Code does not exist |
| 409 | `alias_taken` | Custom alias already used |
| 410 | `gone` | Link expired, deleted, or blocked |
| 422 | `alias_reserved` | Alias is reserved |
| 429 | `rate_limited` | Too many requests |
| 500 | `internal_error` | Unexpected failure |
