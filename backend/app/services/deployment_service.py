"""Deployment orchestration — governance gates, idempotency, concurrency
serialization, and retry/rollback lineage.

Phase 3: actual execution (REQUESTED -> ... -> SUCCEEDED/FAILED) is
delegated to `deployment_worker`, a real in-process asyncio task (ADR-001).
These methods do the synchronous, fast part — validate, gate-check,
persist REQUESTED, schedule the worker — and return immediately; they do
NOT wait for the deployment to finish. Callers that need the final state
either poll `GET /deployments/{id}` or, in tests, use
`deployment_worker.wait_for_deployment`.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.logging_conf import correlation_id_var, get_logger, log_event
from app.models.deployment import Deployment, DeploymentEvent, DeploymentStatus
from app.models.model import LifecycleStage
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.model_repository import ModelRepository
from app.schemas.deployment import DeploymentCreate
from app.services import deployment_worker

logger = get_logger("app.deployment_service")


class DeploymentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = DeploymentRepository(session)
        self.model_repo = ModelRepository(session)

    async def _write_event(
        self, deployment: Deployment, from_status: str | None, to_status: str, message: str
    ) -> None:
        """Writes an event row via deployment_id (not the relationship
        collection) — touching `deployment.events` on a persistent object
        triggers SQLAlchemy to first lazy-load its current state, which
        raises MissingGreenlet outside an awaited context. Callers that
        need the up-to-date event trail re-fetch via `repo.get_deployment`,
        which eager-loads events in a single query (see repository)."""
        event = DeploymentEvent(
            deployment_id=deployment.id,
            from_status=from_status,
            to_status=to_status,
            message=message,
            correlation_id=correlation_id_var.get(),
        )
        self.session.add(event)
        await self.session.flush()

    async def request_deployment(
        self, payload: DeploymentCreate, requested_by: str | None = None
    ) -> tuple[Deployment, bool]:
        """Returns (deployment, created). created=False means an existing
        deployment for this idempotency_key was returned unchanged — the
        duplicate-request-safety acceptance scenario (architecture.md §7).
        A newly created deployment is REQUESTED and still executing
        asynchronously when this returns — see module docstring."""
        existing = await self.repo.get_by_idempotency_key(payload.idempotency_key)
        if existing:
            log_event(
                logger,
                "deployment.idempotent_replay",
                entity_type="Deployment",
                entity_id=existing.id,
                outcome="replayed",
            )
            return existing, False

        version = await self.model_repo.get_version(payload.model_version_id)
        if not version:
            raise NotFoundError(f"Model version '{payload.model_version_id}' not found")

        # Governance gate: PRODUCTION requires an already-APPROVED version.
        # Enforced synchronously, before any async work starts, so it
        # fails fast (architecture.md §6.2 / acceptance scenario 3).
        if payload.environment.upper() == "PRODUCTION" and version.lifecycle_stage not in (
            LifecycleStage.APPROVED,
            LifecycleStage.PRODUCTION,
        ):
            raise ValidationFailedError(
                "Cannot deploy an unapproved model version to PRODUCTION",
                details={
                    "model_version_id": version.id,
                    "current_stage": version.lifecycle_stage,
                    "required_stage": LifecycleStage.APPROVED.value,
                },
            )

        # Serialize concurrent deployments into the same environment for
        # this model (architecture.md Q2) — only one in-flight deployment
        # per (model, environment) at a time.
        sibling_version_ids = [
            v.id for v in await self.model_repo.list_versions(version.model_id)
        ]
        in_flight = await self.repo.get_in_flight_for_environment(
            sibling_version_ids, payload.environment
        )
        if in_flight:
            raise ConflictError(
                f"A deployment is already in progress for this model in "
                f"'{payload.environment}'",
                details={"in_flight_deployment_id": in_flight.id},
            )

        deployment = Deployment(
            model_version_id=payload.model_version_id,
            environment=payload.environment,
            idempotency_key=payload.idempotency_key,
            requested_by=requested_by or payload.requested_by,
            status=DeploymentStatus.REQUESTED,
        )
        deployment = await self.repo.create_deployment(deployment)
        await self._write_event(deployment, None, DeploymentStatus.REQUESTED.value, "Deployment requested")
        await self.session.commit()

        log_event(
            logger,
            "deployment.requested",
            entity_type="Deployment",
            entity_id=deployment.id,
            actor=requested_by,
            outcome="success",
            environment=payload.environment,
        )

        force_success = None if payload.simulate_failure is None else not payload.simulate_failure
        deployment_worker.schedule_deployment_execution(
            deployment.id,
            correlation_id=correlation_id_var.get(),
            force_success=force_success,
        )
        deployment = await self.repo.get_deployment(deployment.id)
        return deployment, True

    async def get_deployment(self, deployment_id: str) -> Deployment:
        deployment = await self.repo.get_deployment(deployment_id)
        if not deployment:
            raise NotFoundError(f"Deployment '{deployment_id}' not found")
        return deployment

    async def list_deployments(self, **filters) -> list[Deployment]:
        return await self.repo.list_deployments(**filters)

    async def retry(
        self, deployment_id: str, requested_by: str | None = None, simulate_failure: bool | None = None
    ) -> Deployment:
        failed = await self.get_deployment(deployment_id)
        if failed.status != DeploymentStatus.FAILED:
            raise ValidationFailedError(
                "Only a FAILED deployment can be retried",
                details={"current_status": failed.status.value},
            )

        retry_idempotency_key = f"{failed.idempotency_key}:retry:{failed.current_attempt + 1}"
        existing = await self.repo.get_by_idempotency_key(retry_idempotency_key)
        if existing:
            # A retry was already requested for this exact failed
            # deployment (e.g. a client retried its own retry request, or
            # — as an idempotent-replay side effect — the original
            # deployment request was itself replayed after already being
            # retried). Same duplicate-request-safety guarantee as
            # request_deployment, not a special case.
            log_event(
                logger,
                "deployment.retry_idempotent_replay",
                entity_type="Deployment",
                entity_id=existing.id,
                outcome="replayed",
            )
            return existing

        new_deployment = Deployment(
            model_version_id=failed.model_version_id,
            environment=failed.environment,
            idempotency_key=retry_idempotency_key,
            requested_by=requested_by or failed.requested_by,
            current_attempt=failed.current_attempt + 1,
            previous_deployment_id=failed.id,
            status=DeploymentStatus.REQUESTED,
        )
        new_deployment = await self.repo.create_deployment(new_deployment)
        await self._write_event(new_deployment, None, DeploymentStatus.REQUESTED.value, f"Retry of {failed.id}")
        await self.session.commit()
        log_event(
            logger,
            "deployment.retry_requested",
            entity_type="Deployment",
            entity_id=new_deployment.id,
            actor=requested_by,
            outcome="success",
            retried_from=failed.id,
        )
        force_success = None if simulate_failure is None else not simulate_failure
        deployment_worker.schedule_deployment_execution(
            new_deployment.id,
            correlation_id=correlation_id_var.get(),
            force_success=force_success,
        )
        return await self.repo.get_deployment(new_deployment.id)

    async def rollback(self, deployment_id: str, requested_by: str | None = None) -> Deployment:
        target = await self.get_deployment(deployment_id)
        if target.status != DeploymentStatus.SUCCEEDED:
            raise ValidationFailedError(
                "Only a SUCCEEDED deployment can be rolled back",
                details={"current_status": target.status.value},
            )

        rollback_idempotency_key = f"{target.idempotency_key}:rollback"
        existing = await self.repo.get_by_idempotency_key(rollback_idempotency_key)
        if existing:
            # Same duplicate-request-safety guarantee as request_deployment
            # and retry — calling rollback twice on the same target (e.g.
            # a client retry, or an idempotent-replay of the original
            # deploy request landing here again) replays, never crashes.
            log_event(
                logger,
                "deployment.rollback_idempotent_replay",
                entity_type="Deployment",
                entity_id=existing.id,
                outcome="replayed",
            )
            return existing

        sibling_version_ids = [
            v.id
            for v in await self.model_repo.list_versions(
                (await self.model_repo.get_version(target.model_version_id)).model_id
            )
        ]
        prior = await self.repo.get_last_succeeded(
            sibling_version_ids, target.environment, exclude_id=target.id
        )
        if not prior:
            raise ValidationFailedError(
                "No prior successful deployment exists to roll back to",
                details={"environment": target.environment},
            )

        # Re-validate the rollback target's lifecycle stage at execution
        # time, not just trusting its state from when it was deployed
        # (architecture.md Q7) — it may have been archived since.
        prior_version = await self.model_repo.get_version(prior.model_version_id)
        if prior_version.lifecycle_stage == LifecycleStage.ARCHIVED:
            raise ValidationFailedError(
                "Rollback target's model version has since been archived",
                details={"model_version_id": prior_version.id},
            )

        rollback_deployment = Deployment(
            model_version_id=prior.model_version_id,
            environment=target.environment,
            idempotency_key=rollback_idempotency_key,
            requested_by=requested_by,
            previous_deployment_id=target.id,
            is_rollback=True,
            status=DeploymentStatus.REQUESTED,
        )
        rollback_deployment = await self.repo.create_deployment(rollback_deployment)
        await self._write_event(
            rollback_deployment, None, DeploymentStatus.REQUESTED.value,
            f"Rollback of {target.id} to prior deployment {prior.id}",
        )
        await self.session.commit()
        log_event(
            logger,
            "deployment.rollback_requested",
            entity_type="Deployment",
            entity_id=rollback_deployment.id,
            actor=requested_by,
            outcome="success",
            rolling_back=target.id,
        )
        # Rollback execution always targets success in the simulation —
        # the validity checks above are what make a rollback "unsafe" or
        # not (architecture.md Q7), not the runtime call itself.
        deployment_worker.schedule_deployment_execution(
            rollback_deployment.id,
            correlation_id=correlation_id_var.get(),
            force_success=True,
        )
        return await self.repo.get_deployment(rollback_deployment.id)
