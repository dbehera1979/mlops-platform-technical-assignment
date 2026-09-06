from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import _utcnow, gen_uuid

# Full ingestion/aggregation pipeline lands in Phase 3 (Monitoring
# Service); the table is defined now so the migration and the
# Deployment<->Metrics relationship are stable from the start.


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id"), index=True
    )
    environment: Mapped[str] = mapped_column(String(50), index=True)
    latency_ms_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms_p99: Mapped[float | None] = mapped_column(Float, nullable=True)
    throughput_rps: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    drift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    availability: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_successful_inference_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
