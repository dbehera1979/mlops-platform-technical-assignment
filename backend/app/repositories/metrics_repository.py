from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrics import MetricSnapshot


class MetricsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_snapshot(self, snapshot: MetricSnapshot) -> MetricSnapshot:
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def list_snapshots(
        self, model_version_id: str, *, environment: str | None = None, limit: int = 100
    ) -> list[MetricSnapshot]:
        stmt = (
            select(MetricSnapshot)
            .where(MetricSnapshot.model_version_id == model_version_id)
            .order_by(MetricSnapshot.recorded_at.desc())
            .limit(limit)
        )
        if environment:
            stmt = stmt.where(MetricSnapshot.environment == environment)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_snapshot(
        self, model_version_id: str, environment: str
    ) -> MetricSnapshot | None:
        stmt = (
            select(MetricSnapshot)
            .where(
                MetricSnapshot.model_version_id == model_version_id,
                MetricSnapshot.environment == environment,
            )
            .order_by(MetricSnapshot.recorded_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
