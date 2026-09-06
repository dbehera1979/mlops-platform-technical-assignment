import enum

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimestampMixin, gen_uuid


class LifecycleStage(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"
    ARCHIVED = "ARCHIVED"


class ApprovalDecision(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Stages a version may move to *directly* via the promotion endpoint.
# PRODUCTION is deliberately excluded here: a version only reaches
# PRODUCTION through a successful Deployment (architecture.md §6.1/§6.2),
# never via a direct promotion call — that's the two-factor control.
ALLOWED_PROMOTIONS: dict[LifecycleStage, set[LifecycleStage]] = {
    LifecycleStage.DRAFT: {LifecycleStage.VALIDATED, LifecycleStage.ARCHIVED},
    LifecycleStage.VALIDATED: {LifecycleStage.APPROVED, LifecycleStage.ARCHIVED},
    LifecycleStage.APPROVED: {LifecycleStage.STAGING, LifecycleStage.ARCHIVED},
    LifecycleStage.STAGING: {LifecycleStage.APPROVED, LifecycleStage.ARCHIVED},
    LifecycleStage.PRODUCTION: {LifecycleStage.ARCHIVED},
    LifecycleStage.ARCHIVED: set(),
}


class Model(Base, TimestampMixin):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    owner_team: Mapped[str | None] = mapped_column(String(200), nullable=True)

    versions: Mapped[list["ModelVersion"]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version_label", name="uq_model_version_label"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(50))
    framework: Mapped[str] = mapped_column(String(100))
    algorithm: Mapped[str] = mapped_column(String(100))
    artifact_uri: Mapped[str] = mapped_column(String(500))
    training_data_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    lifecycle_stage: Mapped[LifecycleStage] = mapped_column(
        Enum(LifecycleStage), default=LifecycleStage.DRAFT, index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Optimistic-concurrency counter — see architecture.md Q2.
    row_version: Mapped[int] = mapped_column(Integer, default=1)

    model: Mapped["Model"] = relationship(back_populates="versions")
    approvals: Mapped[list["ApprovalRecord"]] = relationship(
        back_populates="model_version", cascade="all, delete-orphan"
    )


class ApprovalRecord(Base, TimestampMixin):
    __tablename__ = "approval_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id"), index=True
    )
    from_stage: Mapped[LifecycleStage] = mapped_column(Enum(LifecycleStage))
    to_stage: Mapped[LifecycleStage] = mapped_column(Enum(LifecycleStage))
    approved_by: Mapped[str] = mapped_column(String(200))
    decision: Mapped[ApprovalDecision] = mapped_column(Enum(ApprovalDecision))
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    model_version: Mapped["ModelVersion"] = relationship(back_populates="approvals")
