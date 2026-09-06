# MLOps Platform — Architecture

## 1. Context

Industrial organizations increasingly run ML models across multiple plants, lines, and environments (dev / staging / production). Today those models are typically deployed ad hoc — no consistent registry, no approval gate, no uniform way to see what's running where, no safe rollback path when a model regresses in the field.

This platform gives ML and platform teams a single system of record for:

- **What models exist**, in what versions, trained on what data, with what metadata.
- **What state each version is in** (draft → validated → approved → staging → production → archived) and who approved the promotion.
- **What's deployed where**, with full deployment history and a safe retry/rollback path.
- **How each production model is behaving** — latency, throughput, error rate, quality, drift, availability.

The system is a **platform**, not a model-training tool. Training and scoring logic are out of scope; the platform manages the *lifecycle* of artifacts that are trained elsewhere.

## 2. Scope

**In scope**
- Model & version registry with metadata and audit trail
- Approval / lifecycle promotion workflow with governance gates
- Deployment request → execution → status tracking, as an asynchronous workflow with retry and rollback
- Monitoring metrics ingestion/aggregation and dashboard views
- Angular operational UI over all of the above
- Idempotent APIs, structured logging, correlation IDs, health checks
- CI pipeline, containerized local run (`docker compose up`)

**Out of scope (see `known-limitations.md`)**
- Actual model training / experiment tracking (that's the job of a tool like MLflow / Weights & Biases upstream of this system)
- Real inference serving — deployments and metrics are simulated against a pluggable `ModelRuntime` interface
- Full multi-tenant isolation, SSO — designed for, not fully implemented
- Real message broker infra (Kafka/Redis)

## 3. Architecture Overview

Layered, modular-monolith backend (clear internal service boundaries, single deployable process) fronted by a decoupled Angular SPA, backed by a relational store, with an in-process asynchronous worker for long-running
deployment/monitoring workflows.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Angular UI (SPA)                            │
│  Model Inventory │ Version Detail │ Deployments │ Monitoring │ Events│
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTPS / JSON (typed client, RxJS)
┌────────────────────────────────▼─────────────────────────────────────┐
│                      Auth Boundary (JWT bearer, RBAC)                │
├──────────────────────────────────────────────────────────────────────┤
│                        FastAPI API Layer                             │
│   Routers: models · deployments · metrics · health                   │
├────────────────┬────────────────┬────────────────┬───────────────────┤
│ Model Registry │  Deployment    │  Monitoring    │  Shared: audit,   │
│    Service     │   Service      │   Service      │  idempotency,     │
│                │                │                │  correlation-id   │
├────────────────┴───────┬────────┴───────┬────────┴───────────────────┤
│   Repository / ORM (SQLAlchemy)         │  Async Worker (asyncio)    │
│   SQLite (dev) / PostgreSQL (prod)      │  Deployment executor,      │
│                                         │  metric aggregator         │
└──────────────────────────────────────────────────┬───────────────────┘
                                                   │ pluggable interface
                                          ┌────────▼───────────┐
                                          │ External Model     │
                                          │ Runtime (simulated)│
                                          └────────────────────┘
```

Cross-cutting: structured JSON logging + correlation ID propagated from the Angular client through every API call and into worker tasks, so a single `X-Correlation-Id` traces a request across the sync API and the async
follow-up work it triggers.

## 4. Components

| Component | Responsibility | Owns |
|---|---|---|
| **Model Registry Service** | Create models, register versions, enforce lifecycle-stage transitions, approval records | `Model`, `ModelVersion`, `ApprovalRecord` |
| **Deployment Service** | Accept deployment requests, enforce promotion gates (e.g. no `PRODUCTION` deploy of an unapproved version), idempotency, retry/rollback orchestration | `Deployment`, `DeploymentEvent` |
| **Monitoring Service** | Ingest/aggregate metric snapshots, expose rollups per model/version/environment | `MetricSnapshot` |
| **Async Worker** | Executes long-running deployment state transitions and periodic metric aggregation off the request/response cycle | in-process asyncio tasks (see ADR-001) |
| **Auth** | JWT issuance/validation, role claims (`admin`, `approver`, `operator`, `viewer`) | — |
| **Angular UI** | Operational views, client-side state (RxJS), API client isolated behind a service layer (see §12 / Q9) | — |

Each backend service is a Python package with its own router, schemas, service class, and repository — internally modular so it can be split into a separate deployable later without a rewrite.

## 5. Domain Model

```
Model 1───* ModelVersion 1───* ApprovalRecord
                  │
                  │ 1
                  │
                  * 
             Deployment ───* DeploymentEvent
                  │
                  │ (model_version_id, environment)
                  │
                  *
            MetricSnapshot
```

**Model**
`id, name, description, owner_team, created_at, updated_at`

**ModelVersion**
`id, model_id, version_label, framework, algorithm, artifact_uri,
training_data_ref, tags(json), lifecycle_stage
[DRAFT|VALIDATED|APPROVED|STAGING|PRODUCTION|ARCHIVED], created_at,
created_by, updated_at`

**ApprovalRecord**
`id, model_version_id, from_stage, to_stage, approved_by, decision
[APPROVED|REJECTED], reason, created_at` — immutable audit trail of every
lifecycle transition, not just approvals.

**Deployment**
`id, model_version_id, environment, status
[REQUESTED|VALIDATING|DEPLOYING|SUCCEEDED|FAILED|ROLLED_BACK],
idempotency_key (unique), requested_by, current_attempt,
previous_deployment_id (for rollback lineage), created_at, updated_at`

**DeploymentEvent**
`id, deployment_id, from_status, to_status, message, correlation_id,
created_at` — append-only; this *is* the deployment history / timeline.

**MetricSnapshot**
`id, model_version_id, environment, latency_ms_p50, latency_ms_p99,
throughput_rps, error_rate, quality_score, drift_score, availability, last_successful_inference_at, recorded_at`

## 6. Key Workflows

### 6.1 Register model + versions, approve, promote
1. `POST /models` → `Model` created.
2. `POST /models/{id}/versions` → `ModelVersion` created in `DRAFT`.
3. Validation step (schema + artifact URI reachability check) moves `DRAFT → VALIDATED`.
4. An `approver`-role user calls the promotion endpoint; a new `ApprovalRecord` is written and `lifecycle_stage` advances (`VALIDATED → APPROVED`, and later `APPROVED → PRODUCTION` only through a successful deployment — see below). Every transition is audited never overwritten in place.

### 6.2 Deployment request → async execution → status tracking
1. `POST /deployments` with `{model_version_id, environment, idempotency_key}`.
2. **Gate check (synchronous, in the request):** if `environment ==
   PRODUCTION` and `model_version.lifecycle_stage != APPROVED`, reject with 
   `409 Conflict` immediately — this is the "prevent unapproved production deploy" acceptance scenario, and it must fail fast, not after async work starts.
3. If the idempotency key has been seen before, return the **existing** deployment's current state instead of creating a duplicate.
4. Otherwise: create `Deployment{status=REQUESTED}`, write a
   `DeploymentEvent`, return `202 Accepted` with the deployment id, and hand off to the async worker.
5. Worker executes `REQUESTED → VALIDATING → DEPLOYING → SUCCEEDED|FAILED`,
   writing a `DeploymentEvent` at every transition (this is what drives the
   event timeline and what the UI polls / streams).
6. On `SUCCEEDED` into `PRODUCTION`, the model version's lifecycle stage is
   advanced to `PRODUCTION`; any previously-`PRODUCTION` version for that
   model+environment is superseded (kept for rollback lineage).

### 6.3 Retry
`POST /deployments/{id}/retry` is only valid from `FAILED`. It does **not** mutate the failed deployment; it creates a new `Deployment` row with `previous_deployment_id` pointing at the failed one, same idempotency semantics, and re-enters the async pipeline. This keeps the event history honest — a "retry" is a new attempt, not a rewritten past.

### 6.4 Rollback
`POST /deployments/{id}/rollback` is only valid from `SUCCEEDED` (you can only roll back something that actually went live). It finds the prior `SUCCEEDED` deployment for the same `(model_id, environment)`, creates a new `Deployment` targeting that earlier version with status`ROLLED_BACK` on completion, and re-points production traffic (simulated) to it.

## 7. Reliability

- **Idempotency:** every deployment request carries a client-supplied `idempotency_key`, stored with a unique constraint. A duplicate request (network retry, double-click) returns the original deployment's current
  status rather than creating a second one — this is enforced at the database level, not just in application logic, so it holds under concurrent requests.
- **Concurrency on promotion:** `ModelVersion.lifecycle_stage` transitions use an optimistic-concurrency version column; a promotion request that loses a race gets a `409` and must re-read current state before retrying.
- **Rollback safety:** rollback is only offered when a valid prior `SUCCEEDED` deployment exists for that environment; the API returns `422` otherwise. See Q7 for the full state-machine guard.
- **Async/DB reconciliation:** the worker writes deployment status changes transactionally; if the external runtime call "succeeds" but the DB write fails, the worker treats the deployment as `FAILED` and logs a   reconciliation event rather than trusting the external signal.
- **Failure classification:** deployment failures are tagged `TRANSIENT` (retryable automatically-suggested) vs `TERMINAL`(needs human action, e.g. artifact not found), surfaced in the UI.

## 8. Security

- **AuthN:** JWT bearer tokens (short-lived access token; refresh flow documented, not gold-plated for the take-home).
- **AuthZ (RBAC):** roles `admin`, `approver`, `operator`, `viewer`.
  Promotion/approval endpoints require `approver` or `admin`; deployment mutation requires `operator`+; everyone can read.
- **Environment promotion controls:** promoting *into* `PRODUCTION` is the only transition gated by both role **and** lifecycle state — a deliberate two-factor control.
- **Audit:** every state-changing action writes an immutable event/approval row with actor, timestamp, and correlation id — the audit log is a first-class read model, not just DB history.

## 9. Observability

- **Structured logs:** JSON logs, one line per event, including
  `correlation_id`, `actor`, `entity_type`, `entity_id`, `outcome`.
- **Correlation IDs:** generated at the Angular client (or accepted from caller), propagated via `X-Correlation-Id` header through the API and into the async worker task, so a UI action can be traced end-to-end.
- **Metrics:** application metrics (request latency, error rate per route) separate from *domain* metrics (model latency/drift/etc. in `MetricSnapshot`) — don't conflate the two.
- **Health/readiness:** `GET /health` checks DB connectivity and worker liveness; returns component-level status, not just a boolean.
- **OpenTelemetry:** traces planned via OTel SDK auto-instrumentation for FastAPI + SQLAlchemy, exported to an OTLP collector — noted as a near-term roadmap item rather than implemented for the take-home (kept the dependency footprint small to keep `docker compose up` fast).
- **Operational dashboard proposal:** Grafana over Prometheus-scraped app metrics + a materialized view over `MetricSnapshot` for domain metrics; panels per environment: deployment success rate, mean time to rollback, drift-score trend, error-budget burn.

## 10. Scaling & Trade-offs

Summarized here; full reasoning for the two biggest calls is in
`docs/adr/ADR-001-async-execution-strategy.md` and
`docs/adr/ADR-002-persistence-strategy.md`.

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Async execution | In-process `asyncio` task runner | Celery + Redis/RabbitMQ | Take-home needs to run with `docker compose up` and no extra broker; documented migration path to Celery at scale (ADR-001) |
| Persistence | SQLite (dev), SQLAlchemy abstraction for Postgres | Postgres-only from day one | Zero-friction local run for a grader; identical ORM code path migrates via one config change + Alembic (ADR-002) |
| Backend topology | Modular monolith | Microservices from day one | At this scale (take-home / early platform), service-per-domain adds deploy/ops overhead with no throughput benefit yet; internal module boundaries make the future split mechanical (see Q10) |
| API style | Synchronous REST for reads/writes + async worker for long-running work | Fully async/event-driven (Kafka) API | Reads/writes are low-latency CRUD; only deployment execution and metric aggregation are actually long-running — event-driving the whole API would add complexity without matching the access pattern |

## 11. Appendix — Scaling & Governance Q&A

**Q1. How would this scale from 100 to 10,000 models?**
At 100 models the modular monolith + SQLite/Postgres single instance is fine. Growth path: (1) move to Postgres with proper indexing on `(model_id, lifecycle_stage)` and `(deployment.environment, status)`; (2) split the Deployment Service into its own deployable once deployment volume — not model count — is the bottleneck, since deployments are the write-heavy, latency-sensitive path; (3) move the async worker to a real queue (Celery/RQ + Redis, or SQS) so worker throughput scales independently of the API process; (4) registry reads (10k+ models) get a read replica + cached list/search endpoints, since registry reads are far more frequent than writes.

**Q2. How are conflicting promotions prevented?**
Optimistic concurrency: `ModelVersion` carries a `version` (row) counter. A promotion request must supply the version it read; if it doesn't match current state, the update is rejected with `409` and the client re-reads.
This avoids lost updates without taking a DB lock for the whole request. Additionally, promotion *into* `PRODUCTION` is only reachable via a successful `Deployment`, and deployments to the same `(model, environment)` are serialized (see Q7) — so two people approving the same version twice is harmless (idempotent), but two different versions racing to production in the same environment is not possible because the second deployment request finds the environment "busy" (an in-flight deployment for that environment) and is rejected until the first resolves.

**Q3. How is external success / internal DB failure reconciled?**
The worker treats the external runtime call and the DB status write as one logical unit: it writes a `DEPLOYING` event *before* calling the external runtime, then calls it, then writes the outcome. If the external call succeeds but the subsequent DB write throws, the worker does not treat the deployment as done — on next health-check/reconciliation pass it re-queries the external runtime's actual state (via the pluggable runtime interface's`get_status()`), compares to the last durable DB status, and reconciles: external says live + DB says `DEPLOYING` → force-write `SUCCEEDED` with a `reconciled=true` flag on the event, so the audit trail shows it was healed rather than silently corrected.

**Q4. How are multiple model runtimes supported?**
A `ModelRuntime` interface (`deploy()`, `get_status()`, `rollback()`) is implemented per runtime type (e.g. a REST-serving runtime, a batch-scoring runtime, a simulated runtime for tests/demo). `ModelVersion.framework` /
deployment `environment` config selects the concrete implementation via a factory — the Deployment Service never depends on a specific runtime.

**Q5. How would multi-tenancy work?**
`tenant_id` as a first-class column on `Model`, `Deployment`, and `MetricSnapshot`, enforced at the repository layer (every query is tenant-scoped, not just filtered in the API layer, so a missed filter can't leak data). JWT carries `tenant_id`; RBAC roles are per-tenant. At larger scale, tenants with heavy volume can be split to dedicated schemas/databases behind the same repository interface — not designed for now, but the tenant-scoped-repository pattern makes that split additive.

**Q6. How are large metric volumes partitioned?**
`MetricSnapshot` is time-series-shaped and write-heavy. Plan: partition by `recorded_at` (monthly range partitions in Postgres), with an aggregation job rolling raw snapshots into hourly/daily rollups for dashboard queries older than N days, and a retention policy dropping raw partitions after a window. The API always queries rollups for anything older than "recent", so dashboard latency doesn't degrade as history grows.

**Q7. How is unsafe rollback prevented?**
Rollback is a state-machine-guarded operation, not a free action: (1) only allowed from a `SUCCEEDED` deployment; (2) only if a prior `SUCCEEDED` deployment exists for the same `(model_id, environment)` to roll back *to*; (3) the target version's lifecycle stage is re-validated at rollback time (not just at its original deploy time) in case it was archived since; (4) rollback creates a new tracked `Deployment`, so if the rollback itself fails, the system is never left in an ambiguous "rolling back" limbo — it's just another deployment attempt with its own event trail.

**Q8. How are zero-downtime schema migrations handled?**
Alembic migrations follow an expand/contract pattern: additive changes (new nullable column, new table) ship and deploy first; the application is updated to write to both old/new shape if needed; a backfill migration
runs; only then does a later migration drop the old column, after confirming no code path reads it. CI runs `alembic upgrade head` against a throwaway DB as a migration-safety check on every PR.

**Q9. How is Angular isolated from backend internals?**
The frontend never talks to the domain model directly — it consumes a versioned REST contract described in `api-design.md`, with TypeScript interfaces generated from the same Pydantic schemas the backend validates
against (kept in sync via a shared schema-export step in CI). All HTTP calls go through a single `ApiService` layer; feature components depend on Angular services and RxJS observables, never on `HttpClient` directly —
so a backend refactor (e.g. splitting Deployment Service out) is invisible to the UI as long as the contract holds.

**Q10. How would work be split across teams?**
Along the same seams as the domain services: a **Registry** team (model/version/approval), a **Deployment & Runtime** team (deployment state machine, runtime adapters), a **Monitoring** team (metrics ingestion, aggregation, dashboards), and a **Platform/UI** team owning the Angular shell, shared component library, and API-contract stewardship. The modular monolith's package boundaries map 1:1 to these teams today, so the org
split and the eventual service split are the same seam — reorganizing people doesn't force re-architecting code.
