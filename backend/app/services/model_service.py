"""Model Registry business logic.

Owns: model/version creation, lifecycle promotion with optimistic
concurrency, approval audit trail. Deliberately excludes PRODUCTION from
the set of directly-promotable stages — see ALLOWED_PROMOTIONS — because
PRODUCTION is only reached via a successful Deployment (the two-factor
control described in architecture.md §8/Q2).
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.logging_conf import get_logger, log_event
from app.models.model import (
    ALLOWED_PROMOTIONS,
    ApprovalRecord,
    LifecycleStage,
    Model,
    ModelVersion,
)
from app.repositories.model_repository import ModelRepository
from app.schemas.model import ModelCreate, ModelVersionCreate, PromotionRequest

logger = get_logger("app.model_service")


class ModelService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ModelRepository(session)

    async def create_model(self, payload: ModelCreate) -> Model:
        existing = await self.repo.get_model_by_name(payload.name)
        if existing:
            raise ConflictError(
                f"A model named '{payload.name}' already exists",
                details={"model_id": existing.id},
            )
        model = Model(
            name=payload.name,
            description=payload.description,
            owner_team=payload.owner_team,
        )
        model = await self.repo.create_model(model)
        await self.session.commit()
        log_event(
            logger,
            "model.created",
            entity_type="Model",
            entity_id=model.id,
            outcome="success",
        )
        return model

    async def get_model(self, model_id: str) -> Model:
        model = await self.repo.get_model(model_id)
        if not model:
            raise NotFoundError(f"Model '{model_id}' not found")
        return model

    async def list_models(self, *, search: str | None = None) -> list[Model]:
        return await self.repo.list_models(search=search)

    async def register_version(
        self, model_id: str, payload: ModelVersionCreate
    ) -> ModelVersion:
        await self.get_model(model_id)  # 404s if missing
        existing = await self.repo.get_version_by_label(model_id, payload.version_label)
        if existing:
            raise ConflictError(
                f"Version '{payload.version_label}' already exists for this model",
                details={"model_version_id": existing.id},
            )
        version = ModelVersion(
            model_id=model_id,
            version_label=payload.version_label,
            framework=payload.framework,
            algorithm=payload.algorithm,
            artifact_uri=payload.artifact_uri,
            training_data_ref=payload.training_data_ref,
            tags=payload.tags,
            created_by=payload.created_by,
            lifecycle_stage=LifecycleStage.DRAFT,
        )
        version = await self.repo.create_version(version)
        await self.session.commit()
        log_event(
            logger,
            "model_version.registered",
            entity_type="ModelVersion",
            entity_id=version.id,
            actor=payload.created_by,
            outcome="success",
            model_id=model_id,
        )
        return version

    async def list_versions(self, model_id: str) -> list[ModelVersion]:
        await self.get_model(model_id)
        return await self.repo.list_versions(model_id)

    async def get_version(self, version_id: str) -> ModelVersion:
        version = await self.repo.get_version(version_id)
        if not version:
            raise NotFoundError(f"Model version '{version_id}' not found")
        return version

    async def promote_version(
        self, version_id: str, payload: PromotionRequest
    ) -> ModelVersion:
        version = await self.get_version(version_id)

        # Optimistic concurrency: caller must have read the current
        # row_version. A stale write loses the race (architecture.md Q2).
        if version.row_version != payload.expected_row_version:
            raise ConflictError(
                "Model version was modified by another request; re-read and retry",
                details={
                    "current_row_version": version.row_version,
                    "expected_row_version": payload.expected_row_version,
                },
            )

        allowed = ALLOWED_PROMOTIONS.get(version.lifecycle_stage, set())
        if payload.to_stage not in allowed:
            raise ValidationFailedError(
                f"Cannot promote from {version.lifecycle_stage} to {payload.to_stage}",
                details={
                    "current_stage": version.lifecycle_stage,
                    "allowed_next_stages": sorted(s.value for s in allowed),
                },
            )

        record = ApprovalRecord(
            model_version_id=version.id,
            from_stage=version.lifecycle_stage,
            to_stage=payload.to_stage,
            approved_by=payload.approved_by,
            decision=payload.decision,
            reason=payload.reason,
        )
        await self.repo.add_approval_record(record)

        if payload.decision.value == "APPROVED":
            version.lifecycle_stage = payload.to_stage
        version.row_version += 1

        await self.session.commit()
        log_event(
            logger,
            "model_version.promotion",
            entity_type="ModelVersion",
            entity_id=version.id,
            actor=payload.approved_by,
            outcome=payload.decision.value,
            to_stage=payload.to_stage.value,
        )
        return version
