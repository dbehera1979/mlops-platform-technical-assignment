import pytest

from app.core.exceptions import ConflictError, ValidationFailedError
from app.models.model import ApprovalDecision, LifecycleStage
from app.schemas.model import ModelCreate, ModelVersionCreate, PromotionRequest
from app.services.model_service import ModelService


@pytest.mark.asyncio
async def test_create_model(db_session):
    service = ModelService(db_session)
    model = await service.create_model(ModelCreate(name="fraud-detector"))
    assert model.id
    assert model.name == "fraud-detector"


@pytest.mark.asyncio
async def test_duplicate_model_name_conflicts(db_session):
    service = ModelService(db_session)
    await service.create_model(ModelCreate(name="fraud-detector"))
    with pytest.raises(ConflictError):
        await service.create_model(ModelCreate(name="fraud-detector"))


@pytest.mark.asyncio
async def test_register_two_versions(db_session):
    service = ModelService(db_session)
    model = await service.create_model(ModelCreate(name="fraud-detector"))
    v1 = await service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )
    v2 = await service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v2", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v2",
        ),
    )
    versions = await service.list_versions(model.id)
    assert {v.id for v in versions} == {v1.id, v2.id}
    assert v1.lifecycle_stage == LifecycleStage.DRAFT


@pytest.mark.asyncio
async def test_duplicate_version_label_conflicts(db_session):
    """Regression test: registering the same version_label twice for a
    model used to raise an unhandled 500 (a raw IntegrityError from the
    unique constraint) instead of a proper 409 CONFLICT — found while
    verifying the seed script's re-run safety."""
    service = ModelService(db_session)
    model = await service.create_model(ModelCreate(name="fraud-detector"))
    await service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )
    with pytest.raises(ConflictError):
        await service.register_version(
            model.id,
            ModelVersionCreate(
                version_label="v1", framework="sklearn", algorithm="xgboost",
                artifact_uri="s3://bucket/v1-again",
            ),
        )


@pytest.mark.asyncio
async def test_promote_version_happy_path(db_session):
    service = ModelService(db_session)
    model = await service.create_model(ModelCreate(name="fraud-detector"))
    version = await service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )
    original_row_version = version.row_version
    promoted = await service.promote_version(
        version.id,
        PromotionRequest(
            to_stage=LifecycleStage.VALIDATED,
            approved_by="approver",
            expected_row_version=original_row_version,
        ),
    )
    assert promoted.lifecycle_stage == LifecycleStage.VALIDATED
    assert promoted.row_version == original_row_version + 1


@pytest.mark.asyncio
async def test_promote_version_stale_row_version_conflicts(db_session):
    service = ModelService(db_session)
    model = await service.create_model(ModelCreate(name="fraud-detector"))
    version = await service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )
    with pytest.raises(ConflictError):
        await service.promote_version(
            version.id,
            PromotionRequest(
                to_stage=LifecycleStage.VALIDATED,
                approved_by="approver",
                expected_row_version=version.row_version + 99,
            ),
        )


@pytest.mark.asyncio
async def test_promote_version_illegal_transition_rejected(db_session):
    service = ModelService(db_session)
    model = await service.create_model(ModelCreate(name="fraud-detector"))
    version = await service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )
    # DRAFT -> PRODUCTION is never a legal direct promotion.
    with pytest.raises(ValidationFailedError):
        await service.promote_version(
            version.id,
            PromotionRequest(
                to_stage=LifecycleStage.PRODUCTION,
                approved_by="approver",
                expected_row_version=version.row_version,
            ),
        )
