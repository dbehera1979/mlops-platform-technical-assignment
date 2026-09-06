# MLOps Platform

A representative MLOps platform — model registry, deployment lifecycle and monitoring for an industrial organization running many ML models across plants and environments. Python/FastAPI backend, Angular operational UI.

## Problem Statement

Industrial organizations run many ML models across plants and environments with no consistent way to know what's deployed where, no approval gate before something reaches production, and no safe path to
undo a bad deployment. This platform gives ML and platform teams a single system of record for:

- **What models exist**, in what versions, with what metadata, framework and training-data lineage
- **What lifecycle stage each version is in** (`DRAFT → VALIDATED → APPROVED → STAGING → PRODUCTION → ARCHIVED`) and who approved each transition
- **What's deployed where**, with full deployment history and a safe retry/rollback path
- **How each production model is behaving** — latency, throughput, quality, drift, error rate, availability

The focus throughout is production-quality engineering — governance gates, idempotency, concurrency safety, audit trails, observability — over sophisticated model training, which is explicitly out of scope.

## Architecture Summary

Layered, modular-monolith backend (clear internal service boundaries, single deployable) behind a decoupled Angular SPA, with an in-process async worker handling long-running deployment execution and metric aggregation.

**The two decisions that shape everything else** (full reasoning, rejected alternatives, and migration triggers in their ADRs):

- **`docs/adr/ADR-001`** — deployment execution and periodic metric aggregation run as in-process `asyncio` tasks, not Celery/a real queue because this needs to run via `docker compose up` with zero extra   infrastructure at this scale. Durability lives in the `Deployment`/`DeploymentEvent` tables, not the task itself, so a crash mid-flight is healed by a reconciliation pass rather than lost.
- **`docs/adr/ADR-002`** — SQLite by default (zero-friction local run), PostgreSQL as a one-config-change production target via SQLAlchemy's engine abstraction. A `postgres` Docker Compose profile is provided.
`architecture.md` covers the full domain model, key workflows (including the exact governance gate that blocks an unapproved PRODUCTION deploy) and a Q&A appendix answering ten scaling/governance questions (conflicting
promotions, external-success/internal-DB-failure reconciliation, multi-runtime support, multi-tenancy, metric partitioning, unsafe-rollback prevention, zero-downtime migrations, frontend/backend isolation, and how work would split across a team).

## Technology Stack

**Backend**
| | |
|---|---|
| Language / runtime | Python 3.12 |
| Framework | FastAPI 0.115 |
| ORM | SQLAlchemy 2.0 (async) |
| Database | SQLite (`aiosqlite`, default) · PostgreSQL (`asyncpg`, prod profile) |
| Migrations | Alembic |
| Auth | JWT (`python-jose`), demo role-based issuer |
| Validation | Pydantic v2 |
| Testing | pytest, pytest-asyncio, httpx |

**Frontend**
| | |
|---|---|
| Framework | Angular 18 (standalone components) |
| UI library | Angular Material 18 + CDK |
| State | RxJS (`BehaviorSubject`-backed services — no NgRx) |
| Language | TypeScript |
| Testing | Karma + Jasmine |

**Infrastructure**
Docker (multi-stage builds, non-root backend user), Docker Compose (SQLite by default, Postgres via `--profile postgres`), nginx (frontend static serving + `/api` reverse proxy), GitHub Actions (backend lint/migrate/test, frontend build/test, Docker image builds).

## Setup and Run Instructions

### Docker Compose (recommended)
- Backend: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:8080

### Signing in

There's no real identity provider (see Known Limitations). Sign in from the login screen by picking one of four demo roles — `admin`, `approver`, `operator`, `viewer` — password is ignored.

### Sample data

The platform starts empty. To populate it with realistic demo data — three models, several versions each across different lifecycle stages, a mix of successful/failed/retried/rolled-back deployments, and the monitoring snapshots that come with reaching PRODUCTION — run:

```bash
make backend-seed
# or directly: cd backend && python scripts/seed_demo_data.py
```

Data lives in `backend/scripts/seed_data.json` — edit it to change what gets seeded without touching the script. The script is genuinely safe to re-run (verified across three consecutive runs): it reuses existing
models/versions by name/label rather than erroring, and every deployment action it takes is idempotency-key-based, so re-running never duplicates data. That safety net caught three real backend bugs — a duplicate version label raised a raw 500 instead of a `409`, and calling `retry` or `rollback` twice against the same deployment did too (both are fixed now, with regression tests: `test_duplicate_version_label_conflicts`,`test_retrying_the_same_failed_deployment_twice_replays_idempotently`,
`test_rolling_back_the_same_deployment_twice_replays_idempotently`).

## Test Commands

```bash
make backend-test         # pytest — 29 tests, backend/tests/
make frontend-test        # karma — see the caveat below
```

Or directly:
```bash
cd backend && pytest -v
cd frontend && npm test -- --watch=false --browsers=ChromeHeadless
```

**Backend: 26/26 passing**, covering every acceptance scenario end to end — see `test-strategy.md`'s scenario-to-test mapping table.

**Frontend: written, not executed here.** Five Jasmine specs exist (`ApiService`, `StatusChipComponent`, `authGuard`, `ModelRegistryService`) but no headless Chrome was available in the environment this was built in. They run in CI against GitHub's pre-installed Chrome — that's their first real execution. See `known-limitations.md`.

## API Documentation Location

- **Interactive (Swagger UI):** `http://localhost:8000/docs`
- **Interactive (ReDoc):** `http://localhost:8000/redoc`
- **Human-readable reference:** `api-design.md` — every endpoint, request/   response shapes, the error envelope format, and the governance rules that aren't obvious from the schema alone (e.g. why `PRODUCTION` is
  never a legal direct promotion target)

## Screenshots

**Not included.** No browser was available in the sandbox this project was built in to actually run the Angular app and capture real screenshots (see `known-limitations.md`) — including a fabricated mockup here would misrepresent what was actually verified. The architecture diagram above is the one visual asset that was actually generated and reviewed.

To see the real UI: follow **Setup and Run Instructions** above, sign in, and visit `/models`, `/models/:id`, `/deployments`, `/monitoring`, and `/events`. Screenshots from that run would be a good addition to this
README — genuinely welcome as a follow-up.

## Sample Workflows

**1. Register, approve, and deploy a model** (the core happy path):
```bash
# Get tokens (repeat with each username for its role)
curl -X POST localhost:8000/auth/token -d "username=operator&password=x"
curl -X POST localhost:8000/auth/token -d "username=approver&password=x"

# Register a model + version (operator token)
curl -X POST localhost:8000/models -H "Authorization: Bearer $OP_TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"fraud-detector"}'
curl -X POST localhost:8000/models/$MODEL_ID/versions -H "Authorization: Bearer $OP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"version_label":"v1","framework":"sklearn","algorithm":"xgboost","artifact_uri":"s3://bucket/v1"}'

# Approve it (approver token, twice: VALIDATED then APPROVED)
curl -X POST localhost:8000/models/versions/$VERSION_ID/promote -H "Authorization: Bearer $AP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_stage":"VALIDATED","approved_by":"approver","expected_row_version":1}'
curl -X POST localhost:8000/models/versions/$VERSION_ID/promote -H "Authorization: Bearer $AP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_stage":"APPROVED","approved_by":"approver","expected_row_version":2}'

# Deploy it (operator token) — 202, executes async
curl -X POST localhost:8000/deployments -H "Authorization: Bearer $OP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_version_id":"'$VERSION_ID'","environment":"PRODUCTION","idempotency_key":"demo-1"}'

# Poll until terminal
curl localhost:8000/deployments/$DEPLOYMENT_ID -H "Authorization: Bearer $OP_TOKEN"
```

**2. Fail, then retry, a deployment:**
```bash
curl -X POST localhost:8000/deployments -H "Authorization: Bearer $OP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_version_id":"'$VERSION_ID'","environment":"STAGING","idempotency_key":"demo-2","simulate_failure":true}'
# ... poll, see status: FAILED ...
curl -X POST "localhost:8000/deployments/$FAILED_ID/retry?simulate_failure=false" -H "Authorization: Bearer $OP_TOKEN"
```

**3. Roll back a production deployment** — requires two prior successful deployments to the same `(model, environment)`; rolls back to the one before the target:
```bash
curl -X POST localhost:8000/deployments/$DEPLOYMENT_ID/rollback -H "Authorization: Bearer $OP_TOKEN"
```

**4. Try to deploy an unapproved version to PRODUCTION** (should fail fast with `422 VALIDATION_FAILED`, before any async work starts) — the acceptance-scenario test for this is
`test_unapproved_version_cannot_deploy_to_production`.

All four flows above are exercised as automated tests — see
`backend/tests/integration/test_api_flow.py` for the exact assertions.

## Known Limitations

Full detail in `known-limitations.md`; summary:

- **Simulated, not real:** model serving (`SimulatedModelRuntime`), metrics (plausible generated values, not real inference traffic), and identity (four hardcoded demo users, no real SSO)
- **Scale trade-offs, made deliberately:** in-process asyncio worker, not Celery (ADR-001); SQLite default, not Postgres (ADR-002); modular monolith, not microservices — each with a documented migration trigger
- **Verification gaps, stated plainly:** frontend unit tests are written but unexecuted (no headless Chrome in the build sandbox); no browser-level end-to-end test exists; Docker images are unbuilt in this environment (no Docker daemon available) — CI is the first real build
- **Explicitly out of scope:** real experiment tracking/training, canary deployments, OpenTelemetry export, rate limiting, i18n

## Future Improvements

swap the async trigger to Celery/RQ once volume justifies it; Postgres in production with metric-table partitioning; OpenTelemetry tracing end-to-end; real SSO/OIDC; webhook notifications on deployment status changes; bulk approve/rollback operations.
