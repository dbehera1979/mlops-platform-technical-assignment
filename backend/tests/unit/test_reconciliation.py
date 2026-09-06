"""architecture.md Q3: verifies a deployment stuck in DEPLOYING (as if
the worker process crashed after calling the runtime but before writing
the outcome) gets healed by reconcile_stuck_deployments, and that the
healing is recorded as `reconciled=True` on its event — an audit trail
distinction between normal execution and a healed state."""
import pytest

from app.models.deployment import Deployment, DeploymentStatus
from app.repositories.deployment_repository import DeploymentRepository
from app.schemas.model import ModelCreate, ModelVersionCreate, PromotionRequest
from app.models.model import LifecycleStage
from app.services import deployment_worker
from app.services.model_service import ModelService


@pytest.mark.asyncio
async def test_reconciliation_heals_stuck_deployment(db_session):
    model_service = ModelService(db_session)
    model = await model_service.create_model(ModelCreate(name="fraud-detector"))
    version = await model_service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )

    # Simulate a worker that crashed after writing DEPLOYING but before
    # resolving to a terminal status — bypass the normal service/worker
    # path and write that state directly.
    repo = DeploymentRepository(db_session)
    stuck = await repo.create_deployment(
        Deployment(
            model_version_id=version.id,
            environment="PRODUCTION",
            idempotency_key="stuck-one",
            status=DeploymentStatus.DEPLOYING,
        )
    )
    await db_session.commit()

    healed_ids = await deployment_worker.reconcile_stuck_deployments()

    assert stuck.id in healed_ids
    healed = await repo.get_deployment(stuck.id)
    # SimulatedModelRuntime.get_status always reports "LIVE" -> reconciled
    # to SUCCEEDED, not silently, but with a reconciled=True event.
    assert healed.status == DeploymentStatus.SUCCEEDED
    reconciliation_events = [e for e in healed.events if e.reconciled]
    assert len(reconciliation_events) == 1
    assert reconciliation_events[0].to_status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_reconciliation_is_idempotent(db_session):
    """Calling it twice with nothing stuck should be a no-op, not an
    error — a periodic sweep must be safe to run repeatedly."""
    healed = await deployment_worker.reconcile_stuck_deployments()
    assert healed == []
    healed_again = await deployment_worker.reconcile_stuck_deployments()
    assert healed_again == []
