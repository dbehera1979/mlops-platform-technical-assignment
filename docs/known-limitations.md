# Known Limitations

Deliberate scope cuts and honest caveats — what's simulated, what's not verified, and what a production version would need instead. Each item notes the reasoning and, where relevant, the roadmap item that addresses it.

## Simulated, not real

- **No real model serving.** `ModelRuntime`/`SimulatedModelRuntime`
  (`backend/app/runtime.py`) stand in for an actual inference backend — deploys have realistic latency and a configurable failure rate, but nothing is actually served. Swapping in a real runtime means implementing the same interface; the Deployment Service and worker don't change.
- **No real inference traffic → simulated metrics.** `MonitoringService` generates plausible-looking latency/throughput/error-rate/drift values rather than ingesting them from real traffic. The ingestion contract
  (`MetricSnapshot`, the rollup/degraded-status logic) is real; the data feeding it isn't.
- **No real identity provider.** Auth is a self-contained JWT issuer with four hardcoded demo users (`admin`/`approver`/`operator`/`viewer`) — see `backend/app/core/security.py`. The dependency shape (`get_current_user`,
  `require_roles`) is what would stay stable behind real OIDC/SSO; only token issuance changes. Passwords are not checked at all in the demo.

## Architectural trade-offs (see ADRs for full reasoning)

- **In-process asyncio worker, not Celery/a real queue** (ADR-001).
  Fine at this scale; a process crash loses in-flight *scheduling* (not history — the DB is the source of truth) until the periodic reconciliation pass or a restart heals it. No horizontal worker scaling.
- **SQLite by default, not Postgres** (ADR-002). Single-writer concurrency model means the optimistic-concurrency and in-flight- serialization logic is exercised far less aggressively locally than it
  would be under real concurrent writers. The logic is correct regardless of engine; only failure *frequency* differs. A `postgres` Docker Compose profile is provided but not load-tested here.
- **Modular monolith, not microservices.** One deployable backend process. Internal package boundaries (registry/deployment/monitoring) are drawn so a future split is mechanical, but no service-to-service network calls, no independent scaling, no per-domain deploy pipeline exist yet.
- **No multi-tenancy enforcement.** `tenant_id` scoping is designed but not implemented — there's exactly one tenant.

## Verification gaps (things I did not confirm myself)

- **Frontend unit tests are unexecuted.** Five Jasmine/Karma specs exist and follow standard `TestBed` patterns, but no headless Chrome was available in the sandbox this was built in to actually run them. They   run in CI (`.github/workflows/ci.yml`) against ubuntu-latest's pre-installed Chrome — that's the first real execution they'll get.
- **No browser-level end-to-end verification.** The login → deploy → watch-it-finish flow was never clicked through in an actual browser by whoever built this. The backend's HTTP-level integration tests exercise the identical contract the frontend calls, which covers most of the risk, but UI rendering/interaction bugs (a broken binding, a dialog that doesn't close, a form that doesn't reset) would not be caught by anything in this repo today.
- **Docker images are not build-verified.** No Docker daemon was available in the build sandbox, so `docker-compose.yml` and both Dockerfiles are unbuilt/untested here — they're written to standard multi-stage patterns (see the `docker-build` CI job, which is the first real build they'll get) but a config or path typo could still exist.
- **Bundle size warning.** The production frontend build exceeds the default 512kB initial-bundle budget (~631kB) — a warning, not a build failure, and expected for a full Material app with five feature areas. Not optimized further (route-level code-splitting is already in place via `loadComponent`; further wins would come from auditing which Material modules each feature actually needs).

## Explicitly out of scope

- Real experiment tracking / model training
- Canary/progressive rollout strategies
- OpenTelemetry tracing
- Rate limiting, request throttling, or abuse protection on the API
- Internationalization/localization of the Angular UI
