"""Repository layer: isolates SQLAlchemy query construction from service
(business-logic) code, and is the layer that would become tenant-scoped
when multi-tenancy is implemented (architecture.md Q5)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import ApprovalRecord, Model, ModelVersion


class ModelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_model(self, model: Model) -> Model:
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_model(self, model_id: str) -> Model | None:
        return await self.session.get(Model, model_id)

    async def get_model_by_name(self, name: str) -> Model | None:
        result = await self.session.execute(select(Model).where(Model.name == name))
        return result.scalar_one_or_none()

    async def list_models(
        self, *, search: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[Model]:
        stmt = select(Model).order_by(Model.name).limit(limit).offset(offset)
        if search:
            stmt = stmt.where(Model.name.ilike(f"%{search}%"))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_version(self, version: ModelVersion) -> ModelVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_version(self, version_id: str) -> ModelVersion | None:
        return await self.session.get(ModelVersion, version_id)

    async def list_versions(self, model_id: str) -> list[ModelVersion]:
        stmt = (
            select(ModelVersion)
            .where(ModelVersion.model_id == model_id)
            .order_by(ModelVersion.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_version_by_label(self, model_id: str, version_label: str) -> ModelVersion | None:
        result = await self.session.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == model_id,
                ModelVersion.version_label == version_label,
            )
        )
        return result.scalar_one_or_none()

    async def add_approval_record(self, record: ApprovalRecord) -> ApprovalRecord:
        self.session.add(record)
        await self.session.flush()
        return record
