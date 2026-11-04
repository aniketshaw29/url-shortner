# ADR-0003: Redirect Status and Caching

- Status: accepted
- Date: 2026-11-04
- Deciders: project owner

## Context

Redirects can use `301 Moved Permanently` or `302 Found`. Browsers cache 301 aggressively; we need expiry, deletion, and click analytics to remain correct. Hot links benefit from caching, but correctness comes first on a URL shortener.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| `301` always | Best cacheability | Browser caches indefinitely; breaks expiry, deletion, analytics |
| `302` + `no-store` | Correct every time | No browser/CDN caching; higher origin load |
| `302` + short TTL | Balances correctness and load | Small staleness window; explicit policy needed |
| `307`/`308` | Preserves method/body | Unnecessary for GET; 308 has the same cache issues |

## Decision

Use `302 Found` with `Cache-Control: no-store` in v1. In Phase 3, allow opt-in `Cache-Control: public, max-age=60, s-maxage=300` for links marked cacheable, keeping `302` so clients revalidate.

## Consequences

- Expiry and deletion are enforced on every request in v1.
- Analytics sees every click in v1.
- Origin and Redis must absorb full read volume until opt-in caching exists.
- A CDN must not be placed in front of redirects until cache semantics and client-IP handling are settled.

## Revisit triggers

- Edge/CDN adoption for redirects.
- Owner demand for cacheable links where analytics accuracy is secondary.
- Analytics pipeline needs sampled rather than complete click data.
