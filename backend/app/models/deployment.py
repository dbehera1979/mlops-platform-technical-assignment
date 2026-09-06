import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimestampMixin, _utcnow, gen_uuid


class DeploymentStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    DEPLOYING = "DEPLOYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


TERMINAL_STATUSES = {
    DeploymentStatus.SUCCEEDED,
    DeploymentStatus.FAILED,
    DeploymentStatus.ROLLED_BACK,
}


class FailureClass(str, enum.Enum):
    TRANSIENT = "TRANSIENT"
    TERMINAL = "TERMINAL"


class Deployment(Base, TimestampMixin):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id"), index=True
    )
    environment: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus), default=DeploymentStatus.REQUESTED, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(200), unique=True, index=True
    )
    requested_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_attempt: Mapped[int] = mapped_column(Integer, default=1)
    # Links a retry/rollback attempt to the deployment it supersedes,
    # forming the lineage used for rollback-target lookup (Q7).
    previous_deployment_id: Mapped[str | None] = mapped_column(
        ForeignKey("deployments.id"), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    failure_class: Mapped[FailureClass | None] = mapped_column(
        Enum(FailureClass), nullable=True
    )
    is_rollback: Mapped[bool] = mapped_column(default=False)

    events: Mapped[list["DeploymentEvent"]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentEvent.created_at",
    )


class DeploymentEvent(Base):
    __tablename__ = "deployment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Set when this transition was written by the reconciliation pass
    # (architecture.md Q3) rather than the normal execution path — lets
    # the audit trail show a state was healed, not silently corrected.
    reconciled: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    deployment: Mapped["Deployment"] = relationship(back_populates="events")
