from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, get_current_user, require_roles
from app.db import get_db
from app.models.deployment import DeploymentStatus
from app.schemas.deployment import DeploymentCreate, DeploymentRead
from app.services.deployment_service import DeploymentService

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.post("", response_model=DeploymentRead)
async def request_deployment(
    payload: DeploymentCreate,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(Role.OPERATOR, Role.ADMIN)),
):
    """202 = newly accepted, executing asynchronously (poll GET to watch
    it finish); 200 = an identical request was already handled — see
    the idempotency-key acceptance scenario in architecture.md §7."""
    service = DeploymentService(session)
    deployment, created = await service.request_deployment(payload, requested_by=user.username)
    status_code = 202 if created else 200
    return JSONResponse(
        status_code=status_code,
        content=DeploymentRead.model_validate(deployment).model_dump(mode="json"),
    )


@router.get("", response_model=list[DeploymentRead])
async def list_deployments(
    model_version_id: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    status: DeploymentStatus | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    service = DeploymentService(session)
    return await service.list_deployments(
        model_version_id=model_version_id, environment=environment, status=status
    )


@router.get("/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(
    deployment_id: str,
    session: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    service = DeploymentService(session)
    return await service.get_deployment(deployment_id)


@router.post("/{deployment_id}/retry", response_model=DeploymentRead)
async def retry_deployment(
    deployment_id: str,
    simulate_failure: bool | None = Query(
        default=None, description="Demo/test only: force a deterministic outcome."
    ),
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(Role.OPERATOR, Role.ADMIN)),
):
    service = DeploymentService(session)
    deployment = await service.retry(
        deployment_id, requested_by=user.username, simulate_failure=simulate_failure
    )
    return JSONResponse(
        status_code=202,
        content=DeploymentRead.model_validate(deployment).model_dump(mode="json"),
    )


@router.post("/{deployment_id}/rollback", response_model=DeploymentRead)
async def rollback_deployment(
    deployment_id: str,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(Role.OPERATOR, Role.ADMIN)),
):
    service = DeploymentService(session)
    deployment = await service.rollback(deployment_id, requested_by=user.username)
    return JSONResponse(
        status_code=202,
        content=DeploymentRead.model_validate(deployment).model_dump(mode="json"),
    )
