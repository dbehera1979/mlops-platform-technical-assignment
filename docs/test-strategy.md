# Test Strategy

## Philosophy

Every acceptance scenario in the assignment maps to at least one automated test, at the layer where it's cheapest to verify correctly: business-rule tests live at the service layer (fast, no HTTP/serialization overhead); contract and auth/RBAC tests live at the HTTP layer, because that's the boundary those concerns actually live on.

## Backend

**Layers:**

| Layer | Location | What it covers |
|---|---|---|
| Unit (service) | `tests/unit/` | Business rules in isolation: promotion gates, optimistic concurrency, idempotency, rollback validity, reconciliation, monitoring rollup logic |
| Integration (HTTP) | `tests/integration/` | The full acceptance-scenario flow through real HTTP requests: auth, RBAC, request/response contracts, error envelope shape |

**What's covered today** (29 tests, see `backend/tests/`):

- Model registry: creation, duplicate-name conflict, version registration, promotion (happy path, stale-row-version conflict, illegal transition)
- Deployment: approved-version-required gate, idempotent replay, concurrent-deployment-to-same-environment conflict, forced failure with failure classification, retry-after-failure, rollback happy path,  rollback-target-archived rejection, retry-only-from-failed
- Reconciliation: a deployment artificially stuck in `DEPLOYING` gets healed and the healing is marked `reconciled=true`; a no-op sweep does nothing (idempotent)
- Monitoring: snapshot simulation, rollup status computation, cross-version aggregation
- Full HTTP flow: registry → approve → deploy → duplicate-request safety → rollback, plus a separate failure → retry flow, driven entirely through `httpx.AsyncClient` against the real FastAPI app (no mocking of the
  service layer)
- RBAC: a `viewer` cannot create a model (403); an unauthenticated request is rejected (401)

**Test isolation:** each test gets a fresh in-memory SQLite database (`StaticPool`-backed so the async driver's single connection is shared correctly). The async deployment worker runs as a detached `asyncio.Task`
outside FastAPI's request-scoped DI, so it needs its own session-factory override to land in that same isolated database — see `tests/conftest.py::db_session` and `app/services/deployment_worker.py`'s `set_session_factory`. Async execution is awaited deterministically via `deployment_worker.wait_for_deployment(id)` rather than sleeping and hoping.

**Migration safety:** CI applies every Alembic migration against a throwaway database on every push — a migration that doesn't apply cleanly fails the build (see `.github/workflows/ci.yml`).

**Not covered / deliberately out of scope for the take-home:**
- Load/concurrency testing under real parallel writers (SQLite's single-writer model makes this less meaningful locally than it would be against Postgres — see ADR-002 and `known-limitations.md`)
- Property-based/fuzz testing of the lifecycle state machine
- Contract testing between frontend and backend beyond manually-kept-in-sync TypeScript interfaces (see `known-limitations.md`)

## Frontend

**Layers:**

| Layer | Location | What it covers |
|---|---|---|
| Component | `*.component.spec.ts` | Presentational logic — e.g. `StatusChipComponent`'s status→color mapping stays consistent and never throws on an unrecognized status |
| Service | `*.service.spec.ts` | `ApiService`'s query-param handling, `ModelRegistryService`'s loading→success/error state transitions, via `HttpClientTestingModule` |
| Guard | `*.guard.spec.ts` | `authGuard` allows/redirects correctly based on auth state |

## Acceptance Scenario Coverage

pass against each mapped to the specific test(s) that verify it.

| # | Scenario | Verified by |
|---|---|---|
| 1 | Register a model and two versions | `test_register_two_versions` (unit), `test_full_registry_to_production_flow` (HTTP) |
| 2 | Approve one version | `test_promote_version_happy_path` (unit), same HTTP flow test |
| 3 | Prevent an unapproved version from Production deployment | `test_unapproved_version_cannot_deploy_to_production` (unit), asserted as a `422` in the HTTP flow test |
| 4 | Deploy an approved version | `test_deploy_approved_version_succeeds` (unit, awaits the real async worker), HTTP flow test |
| 5 | Show monitoring data in Angular | `test_simulate_snapshot_and_rollup` (backend), `MonitoringDashboardComponent` (frontend, seeded automatically on go-live — asserted server-side in the HTTP flow test via `GET /models/{id}/metrics`) |
| 6 | Retry a failed deployment | `test_retry_after_failure_can_succeed` (unit), `test_deployment_failure_and_retry_flow` (HTTP, forced failure then forced-success retry) |
| 7 | Roll back a Production deployment | `test_rollback_happy_path`, `test_rollback_rejected_if_target_version_archived` (unit), HTTP flow test |
| 8 | Handle duplicate deployment requests safely | `test_duplicate_idempotency_key_replays_existing_deployment` (unit), asserted in the HTTP flow test (same `idempotency_key` → same deployment id, `200` not a new `202`) |
| 9 | Surface API failures clearly in the UI | `ApiError`/`errorInterceptor` normalize every backend error envelope into a typed object every feature component branches on (`error.code`) — see `RequestDeploymentDialogComponent` and `PromoteVersionDialogComponent` for the two concrete cases (governance-gate violation, optimistic-concurrency conflict) that get specific, non-generic messages |
| 10 | Verify critical workflows through automated tests | This table, plus `test-strategy.md` in full — 29 backend tests, 0 executed frontend tests (see `known-limitations.md`) |

## Running everything

```bash
make backend-test     # pytest, from repo root
make frontend-test     # karma, headless chrome required
```

Both also run in `.github/workflows/ci.yml` on every push/PR.
