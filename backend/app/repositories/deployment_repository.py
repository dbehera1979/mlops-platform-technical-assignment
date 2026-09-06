from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentStatus,
    TERMINAL_STATUSES,
)


class DeploymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_deployment(self, deployment: Deployment) -> Deployment:
        self.session.add(deployment)
        await self.session.flush()
        return deployment

    async def get_deployment(self, deployment_id: str) -> Deployment | None:
        # Eager-load events: DeploymentRead always serializes the event
        # trail, and doing that via a lazy load outside an awaited
        # context raises MissingGreenlet under the async driver.
        # populate_existing=True forces a refresh of the events collection
        # even when this deployment is already in the session's identity
        # map with a stale (partially loaded) events list from an earlier
        # fetch in the same request.
        stmt = (
            select(Deployment)
            .where(Deployment.id == deployment_id)
            .options(selectinload(Deployment.events))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Deployment | None:
        stmt = (
            select(Deployment)
            .where(Deployment.idempotency_key == key)
            .options(selectinload(Deployment.events))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_deployments(
        self,
        *,
        model_version_id: str | None = None,
        environment: str | None = None,
        status: DeploymentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Deployment]:
        stmt = (
            select(Deployment)
            .options(selectinload(Deployment.events))
            .order_by(Deployment.created_at.desc())
        )
        if model_version_id:
            stmt = stmt.where(Deployment.model_version_id == model_version_id)
        if environment:
            stmt = stmt.where(Deployment.environment == environment)
        if status:
            stmt = stmt.where(Deployment.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_in_flight_for_environment(
        self, model_id_versions: list[str], environment: str
    ) -> Deployment | None:
        """Finds a non-terminal deployment for any version of this model
        in this environment — used to serialize concurrent promotions
        into the same environment (architecture.md Q2)."""
        stmt = select(Deployment).where(
            Deployment.model_version_id.in_(model_id_versions),
            Deployment.environment == environment,
            Deployment.status.notin_(TERMINAL_STATUSES),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_last_succeeded(
        self, model_version_ids: list[str], environment: str, *, exclude_id: str | None = None
    ) -> Deployment | None:
        stmt = (
            select(Deployment)
            .where(
                Deployment.model_version_id.in_(model_version_ids),
                Deployment.environment == environment,
                Deployment.status == DeploymentStatus.SUCCEEDED,
            )
            .order_by(Deployment.created_at.desc())
        )
        if exclude_id:
            stmt = stmt.where(Deployment.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def add_event(self, event: DeploymentEvent) -> DeploymentEvent:
        self.session.add(event)
        await self.session.flush()
        return event
