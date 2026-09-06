"""In-process asyncio deployment worker (ADR-001).

This replaces the Phase 2 synchronous `_execute_stub`: the API layer now
creates a `Deployment{REQUESTED}` and returns immediately (202), and this
module executes the rest of the state machine as a real background
asyncio task, using its own DB session (a request-scoped session is gone
by the time the task runs).

Durability lives in the `Deployment`/`DeploymentEvent` tables, not in the
task itself — every transition is committed before the next one starts.
If the process restarts mid-flight, `reconcile_stuck_deployments` finds
anything left in a non-terminal state and resolves it against the
runtime's own view, per architecture.md Q3.
"""
import asyncio
import logging

from app.db import AsyncSessionLocal
from app.logging_conf import correlation_id_var, get_logger, log_event

# Overridable so tests can point the worker at an isolated in-memory DB
# instead of the app's real engine — the worker runs outside FastAPI's
# request-scoped dependency injection, so it needs its own seam. See
# tests/conftest.py::db_session.
_session_factory = AsyncSessionLocal


def set_session_factory(factory) -> None:
    global _session_factory
    _session_factory = factory
from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentStatus,
    FailureClass,
)
from app.models.model import LifecycleStage
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.model_repository import ModelRepository
from app.runtime import RuntimeDeployError, get_runtime

logger = get_logger("app.deployment_worker")

# deployment_id -> asyncio.Task, so callers (and tests) can await
# in-flight work instead of racing it. Cleaned up on completion.
_pending_tasks: dict[str, asyncio.Task] = {}


def schedule_deployment_execution(
    deployment_id: str, *, correlation_id: str | None, force_success: bool | None = None
) -> asyncio.Task:
    """Fire-and-forget scheduling from the request path. `force_success`
    (True=succeed, False=fail, None=random) is test/demo-only — see
    DeploymentCreate.simulate_failure."""
    task = asyncio.create_task(
        _execute_deployment(deployment_id, correlation_id, force_success)
    )
    _pending_tasks[deployment_id] = task
    task.add_done_callback(lambda t: _pending_tasks.pop(deployment_id, None))
    return task


async def wait_for_deployment(deployment_id: str) -> None:
    """Test/demo helper: await the in-flight task for a deployment, if
    any. A no-op if the deployment already finished (or was never async
    — e.g. it was returned via idempotent replay)."""
    task = _pending_tasks.get(deployment_id)
    if task:
        await task


async def _write_event(
    repo: DeploymentRepository,
    deployment: Deployment,
    from_status: str | None,
    to_status: str,
    message: str,
    *,
    reconciled: bool = False,
) -> None:
    event = DeploymentEvent(
        deployment_id=deployment.id,
        from_status=from_status,
        to_status=to_status,
        message=message,
        correlation_id=correlation_id_var.get(),
        reconciled=reconciled,
    )
    repo.session.add(event)
    await repo.session.flush()


async def _execute_deployment(
    deployment_id: str, correlation_id: str | None, force_success: bool | None
) -> None:
    token = correlation_id_var.set(correlation_id)
    try:
        async with _session_factory() as session:
            repo = DeploymentRepository(session)
            model_repo = ModelRepository(session)
            deployment = await repo.get_deployment(deployment_id)
            if deployment is None:
                logger.warning("deployment.worker.not_found id=%s", deployment_id)
                return

            deployment.status = DeploymentStatus.VALIDATING
            await _write_event(
                repo, deployment, DeploymentStatus.REQUESTED.value,
                DeploymentStatus.VALIDATING.value, "Validating deployment request",
            )
            await session.commit()

            deployment.status = DeploymentStatus.DEPLOYING
            await _write_event(
                repo, deployment, DeploymentStatus.VALIDATING.value,
                DeploymentStatus.DEPLOYING.value, "Calling model runtime",
            )
            await session.commit()

            runtime = get_runtime()
            version = await model_repo.get_version(deployment.model_version_id)

            try:
                if deployment.is_rollback:
                    await runtime.rollback(
                        deployment_id=deployment.id,
                        model_version_id=deployment.model_version_id,
                        environment=deployment.environment,
                    )
                else:
                    await runtime.deploy(
                        deployment_id=deployment.id,
                        model_version_id=deployment.model_version_id,
                        environment=deployment.environment,
                        force_success=force_success,
                    )
            except RuntimeDeployError as exc:
                deployment.status = DeploymentStatus.FAILED
                deployment.failure_reason = exc.message
                deployment.failure_class = (
                    FailureClass.TRANSIENT if exc.transient else FailureClass.TERMINAL
                )
                await _write_event(
                    repo, deployment, DeploymentStatus.DEPLOYING.value,
                    DeploymentStatus.FAILED.value,
                    f"{deployment.failure_class.value}: {exc.message}",
                )
                await session.commit()
                log_event(
                    logger, "deployment.failed", entity_type="Deployment",
                    entity_id=deployment.id, outcome="FAILED",
                    failure_class=deployment.failure_class.value,
                )
                return

            final_status = (
                DeploymentStatus.ROLLED_BACK if deployment.is_rollback else DeploymentStatus.SUCCEEDED
            )
            deployment.status = final_status
            reached_production = (
                not deployment.is_rollback and deployment.environment.upper() == "PRODUCTION"
            )
            if reached_production:
                version.lifecycle_stage = LifecycleStage.PRODUCTION
            await _write_event(
                repo, deployment, DeploymentStatus.DEPLOYING.value,
                final_status.value,
                "Rollback complete" if deployment.is_rollback else "Deployment succeeded",
            )
            await session.commit()
            log_event(
                logger, "deployment.finished", entity_type="Deployment",
                entity_id=deployment.id, outcome=final_status.value,
            )

            if reached_production:
                # Local import avoids a monitoring_service <-> worker
                # import cycle; this is a fire-and-forget seed snapshot
                # so the dashboard has data immediately after go-live.
                from app.services.monitoring_service import MonitoringService

                monitoring = MonitoringService(session)
                await monitoring.simulate_snapshot(deployment.model_version_id, deployment.environment)
    except Exception:  # noqa: BLE001
        # A crash here is exactly the split-brain case in architecture.md
        # Q3 if the runtime call actually landed. We don't trust our own
        # in-memory view of what happened — leave the row as DEPLOYING and
        # let reconcile_stuck_deployments resolve it against the runtime.
        logger.exception("deployment.worker.crashed id=%s", deployment_id)
    finally:
        correlation_id_var.reset(token)


async def reconcile_stuck_deployments() -> list[str]:
    """architecture.md Q3: finds deployments stuck in a non-terminal
    state (worker crashed, process restarted mid-flight) and asks the
    runtime for ground truth rather than guessing. Returns the ids it
    healed. Safe to call repeatedly (idempotent) — a periodic task in
    production, invoked directly here / from tests for the take-home."""
    healed: list[str] = []
    runtime = get_runtime()
    async with _session_factory() as session:
        repo = DeploymentRepository(session)
        stuck = await repo.list_deployments(status=DeploymentStatus.DEPLOYING, limit=500)
        for deployment in stuck:
            actual = await runtime.get_status(deployment_id=deployment.id)
            if actual == "LIVE":
                deployment.status = DeploymentStatus.SUCCEEDED
                await _write_event(
                    repo, deployment, DeploymentStatus.DEPLOYING.value,
                    DeploymentStatus.SUCCEEDED.value,
                    "Reconciled: runtime reports live but DB write had not completed",
                    reconciled=True,
                )
            else:
                deployment.status = DeploymentStatus.FAILED
                deployment.failure_class = FailureClass.TRANSIENT
                deployment.failure_reason = "Reconciliation: runtime did not confirm deployment"
                await _write_event(
                    repo, deployment, DeploymentStatus.DEPLOYING.value,
                    DeploymentStatus.FAILED.value,
                    "Reconciled: runtime did not confirm a live deployment",
                    reconciled=True,
                )
            healed.append(deployment.id)
        await session.commit()
    return healed
