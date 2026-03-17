# Infrastructure: Prototype → Production

> How we'd take the Redline Service from a Railway demo into a production-grade legal document platform — and the reasoning behind each decision.

---

## 1. Architecture & Infrastructure

Today the entire application runs as a single Railway container: FastAPI serves both the API and the static React frontend, backed by a Railway-managed PostgreSQL instance. Document content is stored directly in PostgreSQL TEXT columns, with some rows reaching 11MB. This works fine for a demo with a handful of users, but several things would need to change for production.

| Layer | Current (Prototype) | Production | Why Change |
|-------|-------------------|------------|------------|
| **Compute** | Single Railway container (FastAPI serves API + static frontend) | ECS Fargate — 2+ stateless pods behind ALB, auto-scaling | A single container is a single point of failure. We need horizontal scaling and health-checked redundancy. |
| **Database** | Railway-managed PostgreSQL, document content stored as TEXT (up to 11MB/row) | RDS PostgreSQL Multi-AZ for metadata + search vectors. **Document content → S3** with DB storing an `s3_key` reference. | 11MB TEXT rows make `pg_dump` slow, cause replication lag spikes, and make VACUUM expensive. S3 handles large objects natively with no row-size penalty. |
| **Cache** | None — every sidebar load hits the DB, every document switch re-fetches | Redis (ElastiCache) — document metadata (5min TTL), search results (1min TTL), rate limit counters | Reduces DB load by roughly 80%. Shared across all pods so cache survives individual pod restarts. |
| **CDN** | None — all traffic routes through Railway's edge | CloudFront — static assets cached indefinitely (content-hashed filenames), `/content` responses cached by `{id}-v{version}` | Sub-50ms asset loads globally. Version-based cache keys mean we never serve stale content without needing manual invalidation. |
| **Search** | PostgreSQL tsvector + GIN index with ILIKE fallback for stop words | Same stack, plus **Elasticsearch** when the corpus exceeds ~10K documents or we need fuzzy/typo-tolerant matching | Postgres FTS is excellent for hundreds of legal documents with exact-phrase queries. Elasticsearch would add relevance tuning and fuzzy matching but introduces a separate cluster to manage and keep in sync. |
| **File Processing** | Synchronous `pdfplumber` in the request handler (blocks 60-80s on scanned PDFs) | Async task queue (SQS + Lambda). Upload returns `202 Accepted`, client polls for completion | Long-running PDF extraction ties up an API pod and risks ALB timeouts. Moving it off the request path keeps the API responsive. |

The most important architectural change is moving document content out of PostgreSQL and into S3. This adds a network hop for content reads, but with CloudFront caching the latency is actually lower than the current path. More importantly, it means PostgreSQL stays lean — backups are fast, replication is smooth, and we're not fighting TOAST compression on every large row.

```
PRODUCTION TOPOLOGY

    Users ─→ CloudFront (CDN) ─→ ALB (TLS + WAF)
                                      │
                        ┌─────────────┼─────────────┐
                        │             │             │
                   [API Pod 1]   [API Pod 2]   [API Pod N]
                        │             │             │
                        └─────────────┼─────────────┘
                                      │
                   ┌──────────────────┼──────────────────┐
                   │                  │                  │
              Redis (Cache)    RDS PostgreSQL         S3 (Content)
              Rate limits      Metadata + FTS         Document bodies
              Session tokens   change_history         Audit archives
```

---

## 2. CI/CD & Deployment

Right now deployment is a manual `railway up` from the CLI — there's no CI pipeline, no staging environment, and rollbacks mean redeploying a previous commit. For production, we'd want automated testing on every push, a staging environment that mirrors production, and deployments that can be rolled back in seconds without redeploying.

The branching model would follow trunk-based development with short-lived feature branches. Every commit to a dev branch triggers a **Pull Request Build (PRB)** — the full test suite (lint, unit tests, integration tests, E2E) must pass before the PR can be merged. No code reaches `main` without a green PRB and at least one reviewer approval. This catches regressions at the earliest possible point, before they affect anyone else.

| Aspect | Current | Production |
|--------|---------|------------|
| **Build** | `railway up` from CLI (uploads source, builds remotely) | GitHub Actions → lint (`ruff`, `eslint`) + test (`pytest`, Playwright E2E) + Docker build → push to ECR |
| **PRB (Pull Request Build)** | None — commits go straight to main | Every push to a feature branch triggers a full CI run. PR cannot merge unless all checks pass. Required reviewer approval. |
| **Tests in CI** | Run manually by the developer | Automated on every push: 28 pytest tests, Playwright E2E against a testcontainers Postgres instance |
| **Staging** | None | Auto-deploys on merge to `main`. Mirrors production topology at 1/4 scale, seeded with anonymized data |
| **Production deploy** | Manual `railway up` | Blue-green via ALB target group switch: new version deploys to a "green" target group, health checks pass, ALB shifts traffic. Old "blue" version stays running for 15 minutes for instant rollback |
| **Migrations** | `Base.metadata.create_all()` + raw SQL `ALTER TABLE` statements on every startup | Alembic migrations run as a CI step before code deploy. Additive changes (new columns) go out before the code that uses them; destructive changes (drop column) go out after the old code is fully retired |
| **Rollback** | Redeploy the previous commit and wait for build | ALB switches traffic back to the previous target group in under 5 seconds |

**Why GitHub Actions over Jenkins?** Jenkins is battle-tested and extremely flexible, but it comes with significant operational overhead — you're managing Jenkins servers, plugins, executor nodes, and keeping them patched and available. For a team our size, that's infrastructure we'd rather not own. GitHub Actions is fully managed, lives where our code already is, has native PR integration (status checks, required checks before merge), and scales to zero when there's nothing to build. If we were in an enterprise with an existing Jenkins installation and dedicated DevOps staff to maintain it, Jenkins would be a reasonable choice. But for a greenfield project, the managed approach lets us focus on the product instead of the CI system.

The single most impactful first step is setting up CI with automated tests and PRB enforcement. Everything else — staging, blue-green, proper migrations — builds on having confidence that your code works before it ships.

---

## 3. Security & Compliance

The prototype has no authentication — every endpoint is publicly accessible. That's obviously the first thing to change. Beyond auth, legal documents have specific compliance requirements around encryption, audit trails, and data residency that need to be addressed before any real customer data touches the system.

| Area | Current | Production | Priority |
|------|---------|------------|----------|
| **Authentication** | None — all endpoints are public | OAuth2/OIDC via an identity provider like Okta or Auth0. Authorization Code flow with PKCE for the SPA. JWT validation middleware on every `/api/*` request. Access tokens stored in memory (not localStorage), refresh tokens in HttpOnly cookies. | **P0** |
| **Authorization** | None — any user can read, edit, or delete any document | Role-based access control (viewer, editor, admin) combined with document-level ACLs. Every query filtered by `org_id` extracted from the JWT so tenants can never see each other's data. | **P0** |
| **Encryption in transit** | Railway provides TLS to the edge, but internal traffic is unencrypted | TLS 1.3 everywhere: ALB terminates external SSL, internal traffic between pods and RDS uses `require_ssl`, Redis connections encrypted in transit | P0 |
| **Encryption at rest** | Railway manages PostgreSQL encryption | RDS AES-256 encryption enabled by default. S3 server-side encryption with KMS customer-managed keys (so we control key rotation). Redis encryption at rest enabled. | P1 |
| **Audit logging** | The `change_history` table records what changed and when, but has no `user_id` — we don't know who made each change | Add `user_id` to every history entry. Log all API access (who viewed which document) to a separate audit stream. Ship audit logs to S3 with Object Lock (WORM) for immutable, tamper-proof 7-year retention. | P1 |
| **GDPR** | No data residency controls, no right-to-erasure endpoint | Deploy in EU region (eu-west-1) for EU customers. Implement a data export endpoint and ensure `DELETE /api/documents/{id}` cascades to all history. Data processing agreement with cloud provider. | P1 |
| **SOC 2** | Not applicable | Access controls (RBAC) ✓, encryption (at rest + transit) ✓, audit logging (immutable) ✓, annual penetration testing, documented incident response runbook | P2 |

One important trade-off: achieving full SOC 2 compliance requires migrating off Railway into a VPC-controlled environment on AWS or GCP. Railway doesn't give us the network-level controls (security groups, private subnets, VPC peering) that auditors expect. This is a significant infrastructure change, but it's necessary before onboarding enterprise customers who require SOC 2 reports.

---

## 4. Scalability & Resilience

The prototype runs on a single container with a single database connection. That's fine for a demo, but production needs to handle concurrent users, survive infrastructure failures, and gracefully manage expensive operations like PDF processing.

| Concern | Current | Production | When to Trigger |
|---------|---------|------------|-----------------|
| **Horizontal scaling** | Single container, single process | ECS auto-scaling based on CPU utilization (<60% target) and request latency (p95 <500ms). Minimum 2 pods for availability, maximum 20 for cost control. | When concurrent users exceed ~10 |
| **Database scaling** | Single PostgreSQL instance handling both reads and writes | Read replicas for search queries (search is read-heavy). PgBouncer sidecar for connection pooling — without it, 20 pods × 10 connections = 200 DB connections, which degrades performance well before hitting the max. | When search latency exceeds 200ms |
| **Failover** | Railway restarts crashed containers (no SLA on recovery time) | RDS Multi-AZ provides automatic failover in under 60 seconds. ECS replaces unhealthy pods within 10 seconds via ALB health checks against `/api/health`. | Day 1 in production — this is table stakes |
| **Async processing** | PDF extraction runs synchronously in the request handler, blocking the event loop for 60-80 seconds on scanned documents | Move to an async task queue (SQS + Lambda or ECS worker). Upload endpoint returns `202 Accepted` with a task ID, client polls for completion or receives a WebSocket notification. | As soon as PDF uploads start causing ALB timeouts |
| **Search evolution** | PostgreSQL FTS with tsvector + GIN index handles the current corpus well (~hundreds of documents) | Add Elasticsearch as a read-only search index, synced via Change Data Capture (Debezium). Search queries route to ES while PostgreSQL tsvector remains as a fallback for single-document search. | When the corpus exceeds ~10K documents, or when users need fuzzy/typo-tolerant search |
| **Multi-region** | Single region (US), deployed on Railway | Active-passive multi-region with cross-region RDS read replica (promotable in a disaster) and S3 cross-region replication | Only when we have international users who need sub-100ms latency |

The key principle here is to avoid over-engineering early. Multi-region is expensive and operationally complex — single-region with Multi-AZ handles 99.9% of real-world failure scenarios at a fraction of the cost. We'd only add regions when user geography actually demands it.

---

## 5. Monitoring & Observability

Right now "monitoring" means checking `railway logs` for errors after someone reports a problem. In production, we need to know about issues before users do — through metrics, structured logging, distributed tracing, and automated alerting.

| Layer | Current | Production |
|-------|---------|------------|
| **Metrics** | `railway logs` (unstructured stdout) | Prometheus + Grafana dashboards tracking API latency (p50/p95/p99), error rates (5xx), database connection utilization, cache hit rates, and search query latency. FastAPI exposes a `/metrics` endpoint via `prometheus-fastapi-instrumentator`. |
| **Logging** | Unstructured `print()` statements to stdout | Structured JSON logs via `structlog`, with every log line containing: timestamp, log level, event name, `doc_id`, `user_id`, `latency_ms`, and `request_id`. Shipped to Splunk via a log forwarder (Fluentd or the Splunk Universal Forwarder) for indexing, querying, and long-term retention. |
| **Tracing** | None — no way to follow a request through the system | OpenTelemetry instrumentation across FastAPI (request lifecycle), SQLAlchemy (query timing), and external calls (S3, Redis). `X-Request-ID` header propagated from ALB through the entire call chain. Visualized in Jaeger or Grafana Tempo. |
| **Alerting** | Railway sends an email when a container crashes | PagerDuty integration with tiered severity: P1 alerts page on-call immediately (API down, error rate spike), P2 alerts during business hours (latency degradation, connection pool pressure), P3 creates a ticket (certificate expiry, disk usage). Alert rules defined in Prometheus Alertmanager. |
| **Uptime monitoring** | None — we find out about downtime when someone complains | Synthetic monitoring: external service pings `/api/health` every 30 seconds from 3 geographic regions. Alerts if 2 consecutive checks fail. |

**Why Prometheus + Grafana over CloudWatch/Datadog for metrics?** CloudWatch is convenient if you're all-in on AWS, but its query language is limited and dashboards are clunky compared to Grafana. Datadog is excellent but expensive (~$23/host/month for infrastructure monitoring, more for APM). Prometheus is open-source, purpose-built for time-series metrics, and pairs naturally with Grafana for visualization. It also runs well on ECS as a sidecar or dedicated task. The main trade-off is operational: we'd need to manage Prometheus storage (or use a managed service like Grafana Cloud or Amazon Managed Prometheus). For a team comfortable running infrastructure, Prometheus is the better long-term investment.

**Why Splunk over CloudWatch Logs/Datadog Logs?** Splunk excels at log analytics at scale — its Search Processing Language (SPL) is far more powerful than CloudWatch Insights for complex queries across millions of log lines. For a legal document platform where audit trail queries ("show me every action user X took on document Y between January and March") are a compliance requirement, Splunk's indexed search and retention policies are purpose-built. The trade-off is cost — Splunk licensing is based on daily ingestion volume, which gets expensive at scale. For early-stage, CloudWatch Logs is fine; Splunk becomes worth it when log volume grows or compliance requirements demand sophisticated audit querying.

The first alerts to set up are the ones that catch cascading failures early:

| Metric | Threshold | Why It Matters |
|--------|-----------|----------------|
| 5xx error rate | >1% for 3 minutes | Something is broken and users are seeing errors |
| API latency p95 | >1 second for 5 minutes | Performance degradation, likely a slow query or resource exhaustion |
| DB connections | >80% of max | Connection pool exhaustion causes cascading request failures |
| Disk usage | >80% | PostgreSQL stops accepting writes when disk is full |

The structured logging piece is worth emphasizing: including `request_id` in every log line means we can trace a single user's request from the ALB access log, through the FastAPI handler, into the database query, and back — without grep-ing through thousands of unrelated log lines in Splunk. That's the difference between a 5-minute debugging session and a 2-hour one.

---

## 6. Operations & Cost

Running on Railway today costs roughly $10/month. Moving to production-grade AWS infrastructure is a meaningful cost increase, but the components are sized conservatively — we'd start small and right-size based on actual usage rather than guessing.

| Component | Prototype (Railway) | Production (AWS) | At Scale (100 pods) |
|-----------|---|---|---|
| Compute | $5/mo | ~$30/mo (2 Fargate pods, 0.5 vCPU / 1GB each) | ~$1,500/mo |
| Database | $5/mo | ~$140/mo (RDS db.t3.medium, Multi-AZ, 100GB gp3) | ~$500/mo |
| Cache | — | ~$15/mo (ElastiCache cache.t3.micro) | ~$50/mo |
| Storage | — | ~$2/mo (S3 Standard, 50GB) | ~$20/mo |
| CDN + LB | — | ~$30/mo (CloudFront + ALB) | ~$200/mo |
| Monitoring | — | ~$0/mo (Prometheus self-hosted) or ~$50/mo (Grafana Cloud) | ~$200/mo |
| **Total** | **~$10/mo** | **~$217-267/mo** | **~$2,470/mo** |

The jump from $10 to ~$250 looks steep, but most of it is RDS Multi-AZ ($140) — that's the price of database high-availability. Without it, a single AZ failure takes down the service entirely. Everything else is modest: two small Fargate pods, a micro Redis instance, and S3 which is essentially free at our scale.

**Cost controls we'd put in place:**

- **Reserved Instances** for RDS — a 1-year commitment saves roughly 40%, bringing the DB cost from $140 to ~$85/month
- **Fargate Savings Plans** for compute — similar commitment-based discount
- **S3 Lifecycle policies** — documents not accessed in 90 days move to Infrequent Access (50% cheaper per GB), change history older than 1 year archives to Glacier
- **Staging scales to zero** outside business hours — Fargate minimum task count of 0 for non-production environments
- **AWS Cost Anomaly Detection** — alerts when daily spend exceeds 150% of the 7-day rolling average, catching runaway resources before the bill arrives
- **Quarterly right-sizing reviews** — most teams over-provision by 2-3x initially. Reviewing actual CPU/memory utilization and downsizing accordingly is the easiest cost win

**Rate limiting** is also a cost control — without it, a single misbehaving client can drive up compute and database costs. We'd implement Redis-backed per-user rate limits in FastAPI middleware:

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| `POST /upload` | 10/min per user | PDF extraction is CPU-intensive |
| `PATCH /documents/{id}` | 30/min per user | Prevents accidental or malicious bulk damage |
| `GET /search` | 60/min per user | ILIKE fallback queries are expensive on large corpora |
| CloudFront edge | 100 req/s per IP | DDoS protection before traffic even reaches our infrastructure |
