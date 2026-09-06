from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, get_current_user, require_roles
from app.db import get_db
from app.schemas.metrics import MetricSnapshotRead
from app.schemas.model import (
    ModelCreate,
    ModelRead,
    ModelVersionCreate,
    ModelVersionRead,
    PromotionRequest,
)
from app.services.model_service import ModelService
from app.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/models", tags=["models"])


@router.post("", response_model=ModelRead, status_code=201)
async def create_model(
    payload: ModelCreate,
    session: AsyncSession = Depends(get_db),
    _user=Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
):
    service = ModelService(session)
    return await service.create_model(payload)


@router.get("", response_model=list[ModelRead])
async def list_models(
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    service = ModelService(session)
    return await service.list_models(search=search)


@router.get("/{model_id}", response_model=ModelRead)
async def get_model(
    model_id: str,
    session: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    service = ModelService(session)
    return await service.get_model(model_id)


@router.post("/{model_id}/versions", response_model=ModelVersionRead, status_code=201)
async def register_version(
    model_id: str,
    payload: ModelVersionCreate,
    session: AsyncSession = Depends(get_db),
    _user=Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
):
    service = ModelService(session)
    return await service.register_version(model_id, payload)


@router.get("/{model_id}/versions", response_model=list[ModelVersionRead])
async def list_versions(
    model_id: str,
    session: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    service = ModelService(session)
    return await service.list_versions(model_id)


@router.post("/versions/{version_id}/promote", response_model=ModelVersionRead)
async def promote_version(
    version_id: str,
    payload: PromotionRequest,
    session: AsyncSession = Depends(get_db),
    _user=Depends(require_roles(Role.APPROVER, Role.ADMIN)),
):
    service = ModelService(session)
    return await service.promote_version(version_id, payload)


@router.get("/{model_id}/metrics")
async def get_model_metrics(
    model_id: str,
    session: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Latency/throughput/error-rate/quality/drift/availability snapshots
    across every version of this model, newest first (architecture.md
    §5 MetricSnapshot). See MonitoringService for the simulated-data
    caveat — no real inference traffic exists in this take-home."""
    service = ModelService(session)
    await service.get_model(model_id)  # 404s if missing
    monitoring = MonitoringService(session)
    snapshots = await monitoring.get_snapshots_for_model(model_id)
    return {
        "model_id": model_id,
        "snapshots": [MetricSnapshotRead.model_validate(s) for s in snapshots],
    }
