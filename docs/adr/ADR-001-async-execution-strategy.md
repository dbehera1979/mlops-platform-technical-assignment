# ADR-001: Asynchronous Execution Strategy for Deployment & Monitoring Workflows

## Context

Deployment execution (`REQUESTED → VALIDATING → DEPLOYING → SUCCEEDED/FAILED`) and metric aggregation are long-running relative to a normal HTTP request/response cycle. They must not block the API, must be retryable, and must be observable (event history, correlation IDs).

Two realistic options:

1. **In-process async task runner** — `asyncio` tasks scheduled from the FastAPI process, backed by a durable `Deployment`/`DeploymentEvent` table as the source of truth (not an in-memory queue).
2. **Dedicated task queue** — Celery (or RQ/Dramatiq) with Redis or RabbitMQ as broker, workers as separate processes/containers.

## Decision

Use an **in-process asyncio task runner** for this platform's current scale (take-home / early-stage platform), with the deployment/event tables as the durable state — the queue is a convenience, not the system of record. The design is explicitly a stepping stone: the worker's task interface (`execute_deployment(deployment_id)`) has no dependency on being in-process, so swapping the *trigger mechanism* to Celery is a localized change, not a rewrite.

## Rationale

- **Operational simplicity for the target scale.** This needs to run via `docker compose up` with no additional broker infrastructure — a real constraint for a take-home a reviewer needs to run locally.
- **Durability is in the database, not the queue.** Because every status transition is written to `Deployment`/`DeploymentEvent` before/after the external call, a process restart loses in-flight *scheduling* but not   *history* — a reconciliation pass on startup can find any `DEPLOYING`-status rows and re-check them against the runtime.
- **Matches actual load.** At take-home / early-platform volume, thousands of deployments/day is easily handled by a handful of asyncio tasks; Celery's value (worker autoscaling, task routing, retries with backoff policies, multi-language workers) doesn't pay for itself yet.

## Consequences

- **Positive:** zero extra infra to run/demo; simple mental model; full control over correlation-id propagation into tasks.
- **Negative:** worker throughput is capped by the API process; no cross-process work distribution; a crashed API process pauses in-flight work until restart + reconciliation (mitigated, not eliminated, by the DB-first durability above).
- **Migration trigger:** when deployment volume or worker CPU load threatens API responsiveness, or when horizontal worker scaling independent of the API is needed, move the trigger mechanism to Celery + Redis/RabbitMQ (or SQS for a cloud-native path) without changing the domain logic in `execute_deployment`.

## Rejected Alternative

**Celery + Redis/RabbitMQ from day one** — correct production choice at scale, but adds a broker dependency, deployment complexity, and operational surface area that isn't justified yet, and would slow down review/local-run of this take-home for no functional benefit at this volume.