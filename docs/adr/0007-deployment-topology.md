# ADR-0007: Deployment Topology

- Status: accepted
- Date: 2026-11-04
- Deciders: project owner

## Context

The project should be deployed like a small production service: TLS, immutable releases, CI/CD, backups, monitoring, and rollback. The learning goal is operations fundamentals, not Kubernetes. Tier 1 traffic fits on one host.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Single VPS + Docker Compose | Explicit networking/volumes; cheap; teaches ops; easy rollback | Single point of failure; manual host maintenance |
| PaaS (Fly.io/Render) | Least ops; managed TLS/deploys | Hides most infrastructure learning; SQLite/volume constraints vary |
| Kubernetes | Scales; declarative | Disproportionate complexity for one service and one SQLite file |
| Serverless + managed DB | Scales to zero; managed backups | Cold starts; SQLite not a fit; different learning path |

## Decision

One 2 vCPU / 4GB Linux VPS (Hetzner CX22 or equivalent), Ubuntu 24.04 LTS, running Docker Compose:

- **Caddy** for TLS, HTTP/3, security headers, reverse proxy
- **FastAPI** container with 2 Uvicorn workers, non-root
- **SQLite** on the host SSD via bind mount, WAL mode
- **Redis** internal-only, no persistence
- **Litestream** replicating SQLite WAL to S3-compatible object storage
- **GitHub Actions** building images to GHCR and deploying over SSH
- External uptime checks, Grafana Cloud/Sentry for metrics and errors

No CDN in front of redirects initially. No multi-host access to the SQLite file.

## Consequences

- Cost ~$6–10/month.
- Deploys have a 3–10 second restart gap; rollback is redeploying the previous image tag.
- Host loss is an outage until restore completes (target RTO <30 minutes).
- Backups and restore drills are mandatory, not optional.
- Staging can share the host with a separate compose project and data directory.
- Blue-green with two API containers sharing SQLite is a Phase 6 stretch, not the default.

## Revisit triggers

- Availability requirement >99.5% or a real need for zero-downtime deploys.
- Writes >50/s, DB >20GB, or restore >1 hour.
- Need for multi-region, read replicas, or managed failover.
- Operational toil of host maintenance exceeds the learning value.
