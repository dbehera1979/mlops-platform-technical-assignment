import pytest

from app.core.exceptions import ConflictError, ValidationFailedError
from app.models.deployment import DeploymentStatus, FailureClass
from app.models.model import LifecycleStage
from app.schemas.deployment import DeploymentCreate
from app.schemas.model import ModelCreate, ModelVersionCreate, PromotionRequest
from app.services import deployment_worker
from app.services.deployment_service import DeploymentService
from app.services.model_service import ModelService


async def _make_approved_version(db_session):
    model_service = ModelService(db_session)
    model = await model_service.create_model(ModelCreate(name="fraud-detector"))
    version = await model_service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )
    version = await model_service.promote_version(
        version.id,
        PromotionRequest(
            to_stage=LifecycleStage.VALIDATED, approved_by="approver",
            expected_row_version=version.row_version,
        ),
    )
    version = await model_service.promote_version(
        version.id,
        PromotionRequest(
            to_stage=LifecycleStage.APPROVED, approved_by="approver",
            expected_row_version=version.row_version,
        ),
    )
    return version


@pytest.mark.asyncio
async def test_deploy_approved_version_succeeds(db_session):
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    deployment, created = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="key-1", simulate_failure=False,
        ),
        requested_by="operator",
    )
    assert created is True
    assert deployment.status == DeploymentStatus.REQUESTED  # still async at this point

    await deployment_worker.wait_for_deployment(deployment.id)
    deployment = await service.get_deployment(deployment.id)

    assert deployment.status == DeploymentStatus.SUCCEEDED
    statuses = [e.to_status for e in deployment.events]
    assert statuses == ["REQUESTED", "VALIDATING", "DEPLOYING", "SUCCEEDED"]


@pytest.mark.asyncio
async def test_deploy_with_forced_failure(db_session):
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    deployment, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="fail-key", simulate_failure=True,
        )
    )
    await deployment_worker.wait_for_deployment(deployment.id)
    deployment = await service.get_deployment(deployment.id)

    assert deployment.status == DeploymentStatus.FAILED
    assert deployment.failure_reason is not None
    assert deployment.failure_class in (FailureClass.TRANSIENT, FailureClass.TERMINAL)
    assert deployment.events[-1].to_status == "FAILED"


@pytest.mark.asyncio
async def test_retry_after_failure_can_succeed(db_session):
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    deployment, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="fail-then-retry", simulate_failure=True,
        )
    )
    await deployment_worker.wait_for_deployment(deployment.id)
    failed = await service.get_deployment(deployment.id)
    assert failed.status == DeploymentStatus.FAILED

    retried = await service.retry(failed.id, requested_by="operator", simulate_failure=False)
    assert retried.previous_deployment_id == failed.id
    assert retried.current_attempt == failed.current_attempt + 1

    await deployment_worker.wait_for_deployment(retried.id)
    retried = await service.get_deployment(retried.id)
    assert retried.status == DeploymentStatus.SUCCEEDED

    # Retrying the original FAILED deployment again should still work
    # (it's still FAILED, independent of its retry's outcome).
    with pytest.raises(ValidationFailedError):
        await service.retry(retried.id, requested_by="operator")  # retried is SUCCEEDED now


@pytest.mark.asyncio
async def test_unapproved_version_cannot_deploy_to_production(db_session):
    model_service = ModelService(db_session)
    model = await model_service.create_model(ModelCreate(name="fraud-detector"))
    draft_version = await model_service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )
    service = DeploymentService(db_session)
    with pytest.raises(ValidationFailedError):
        await service.request_deployment(
            DeploymentCreate(
                model_version_id=draft_version.id, environment="PRODUCTION",
                idempotency_key="key-1",
            )
        )


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_replays_existing_deployment(db_session):
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    first, first_created = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="dup-key", simulate_failure=False,
        )
    )
    second, second_created = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="dup-key",
        )
    )
    assert first_created is True
    assert second_created is False
    assert first.id == second.id
    await deployment_worker.wait_for_deployment(first.id)


@pytest.mark.asyncio
async def test_concurrent_deployment_to_same_environment_conflicts(db_session):
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    first, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="first-inflight",
        )
    )
    # `first` is still REQUESTED/executing — a second, DIFFERENT request
    # for the same (model, environment) must be rejected, not queued.
    with pytest.raises(ConflictError):
        await service.request_deployment(
            DeploymentCreate(
                model_version_id=version.id, environment="PRODUCTION",
                idempotency_key="second-inflight",
            )
        )
    await deployment_worker.wait_for_deployment(first.id)


@pytest.mark.asyncio
async def test_rollback_requires_prior_succeeded_deployment(db_session):
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    deployment, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="only-one", simulate_failure=False,
        )
    )
    await deployment_worker.wait_for_deployment(deployment.id)
    # No PRIOR successful deployment exists (this is the only one) ->
    # rollback should be rejected.
    with pytest.raises(ValidationFailedError):
        await service.rollback(deployment.id, requested_by="operator")


@pytest.mark.asyncio
async def test_rollback_happy_path(db_session):
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    first, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="first", simulate_failure=False,
        )
    )
    await deployment_worker.wait_for_deployment(first.id)
    second, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="second", simulate_failure=False,
        )
    )
    await deployment_worker.wait_for_deployment(second.id)

    rollback_deployment = await service.rollback(second.id, requested_by="operator")
    await deployment_worker.wait_for_deployment(rollback_deployment.id)
    rolled_back = await service.get_deployment(rollback_deployment.id)

    assert rolled_back.status == DeploymentStatus.ROLLED_BACK
    assert rolled_back.previous_deployment_id == second.id


@pytest.mark.asyncio
async def test_rolling_back_the_same_deployment_twice_replays_idempotently(db_session):
    """Regression test: calling rollback() twice against the same target
    deployment used to crash with an unhandled 500 (a raw unique-
    constraint IntegrityError on the rollback's idempotency_key, which is
    derived deterministically from the target's own key) — same class of
    bug as the retry one above. Found via the same seed-script re-run
    verification."""
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    first, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="first", simulate_failure=False,
        )
    )
    await deployment_worker.wait_for_deployment(first.id)
    second, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="second", simulate_failure=False,
        )
    )
    await deployment_worker.wait_for_deployment(second.id)

    first_rollback = await service.rollback(second.id, requested_by="operator")
    await deployment_worker.wait_for_deployment(first_rollback.id)

    second_rollback = await service.rollback(second.id, requested_by="operator")

    assert second_rollback.id == first_rollback.id


@pytest.mark.asyncio
async def test_rollback_rejected_if_target_version_archived(db_session):
    model_service = ModelService(db_session)
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)

    first, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="v1-deploy", simulate_failure=False,
        )
    )
    await deployment_worker.wait_for_deployment(first.id)

    # Register + deploy a v2 so there's something to roll back FROM.
    v2 = await model_service.register_version(
        version.model_id,
        ModelVersionCreate(
            version_label="v2", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v2",
        ),
    )
    v2 = await model_service.promote_version(
        v2.id, PromotionRequest(
            to_stage=LifecycleStage.VALIDATED, approved_by="approver",
            expected_row_version=v2.row_version,
        )
    )
    v2 = await model_service.promote_version(
        v2.id, PromotionRequest(
            to_stage=LifecycleStage.APPROVED, approved_by="approver",
            expected_row_version=v2.row_version,
        )
    )
    second, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=v2.id, environment="PRODUCTION",
            idempotency_key="v2-deploy", simulate_failure=False,
        )
    )
    await deployment_worker.wait_for_deployment(second.id)

    # Archive v1 (the rollback target) after it was successfully deployed.
    v1 = await model_service.get_version(version.id)
    await model_service.promote_version(
        v1.id, PromotionRequest(
            to_stage=LifecycleStage.ARCHIVED, approved_by="approver",
            expected_row_version=v1.row_version,
        )
    )

    with pytest.raises(ValidationFailedError):
        await service.rollback(second.id, requested_by="operator")


@pytest.mark.asyncio
async def test_retry_only_allowed_from_failed(db_session):
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    deployment, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="k1", simulate_failure=False,
        )
    )
    await deployment_worker.wait_for_deployment(deployment.id)
    deployment = await service.get_deployment(deployment.id)
    assert deployment.status == DeploymentStatus.SUCCEEDED

    with pytest.raises(ValidationFailedError):
        await service.retry(deployment.id, requested_by="operator")


@pytest.mark.asyncio
async def test_retrying_the_same_failed_deployment_twice_replays_idempotently(db_session):
    """Regression test: calling retry() twice against the same FAILED
    deployment used to crash with an unhandled 500 (a raw unique-
    constraint IntegrityError on the retry's idempotency_key, which is
    derived deterministically from the failed deployment's own key and
    attempt count — so it collided on the second call). Found while
    verifying the seed script's re-run safety."""
    version = await _make_approved_version(db_session)
    service = DeploymentService(db_session)
    deployment, _ = await service.request_deployment(
        DeploymentCreate(
            model_version_id=version.id, environment="PRODUCTION",
            idempotency_key="will-fail", simulate_failure=True,
        )
    )
    await deployment_worker.wait_for_deployment(deployment.id)
    failed = await service.get_deployment(deployment.id)
    assert failed.status == DeploymentStatus.FAILED

    first_retry = await service.retry(failed.id, requested_by="operator", simulate_failure=True)
    await deployment_worker.wait_for_deployment(first_retry.id)

    second_retry = await service.retry(failed.id, requested_by="operator", simulate_failure=True)

    assert second_retry.id == first_retry.id
