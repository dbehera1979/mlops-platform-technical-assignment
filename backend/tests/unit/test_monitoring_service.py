import pytest

from app.models.model import LifecycleStage
from app.schemas.model import ModelCreate, ModelVersionCreate, PromotionRequest
from app.services.model_service import ModelService
from app.services.monitoring_service import MonitoringService


@pytest.mark.asyncio
async def test_simulate_snapshot_and_rollup(db_session):
    model_service = ModelService(db_session)
    model = await model_service.create_model(ModelCreate(name="churn-model"))
    version = await model_service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="pytorch", algorithm="lstm",
            artifact_uri="s3://bucket/v1",
        ),
    )

    monitoring = MonitoringService(db_session)
    rollup_before = await monitoring.get_rollup(version.id, "PRODUCTION")
    assert rollup_before["monitoring_status"] == "NO_DATA"

    snapshot = await monitoring.simulate_snapshot(version.id, "PRODUCTION")
    assert snapshot.model_version_id == version.id
    assert 0.0 <= snapshot.error_rate <= 1.0
    assert snapshot.availability is not None

    rollup_after = await monitoring.get_rollup(version.id, "PRODUCTION")
    assert rollup_after["monitoring_status"] in ("HEALTHY", "DEGRADED")
    assert rollup_after["latest"].id == snapshot.id


@pytest.mark.asyncio
async def test_get_snapshots_for_model_aggregates_versions(db_session):
    model_service = ModelService(db_session)
    model = await model_service.create_model(ModelCreate(name="fraud-detector"))
    v1 = await model_service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v1", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v1",
        ),
    )
    v2 = await model_service.register_version(
        model.id,
        ModelVersionCreate(
            version_label="v2", framework="sklearn", algorithm="xgboost",
            artifact_uri="s3://bucket/v2",
        ),
    )
    monitoring = MonitoringService(db_session)
    await monitoring.simulate_snapshot(v1.id, "STAGING")
    await monitoring.simulate_snapshot(v2.id, "PRODUCTION")

    snapshots = await monitoring.get_snapshots_for_model(model.id)
    assert {s.model_version_id for s in snapshots} == {v1.id, v2.id}
