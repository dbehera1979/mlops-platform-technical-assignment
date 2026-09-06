from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MetricSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    model_version_id: str
    environment: str
    latency_ms_p50: Optional[float] = None
    latency_ms_p99: Optional[float] = None
    throughput_rps: Optional[float] = None
    error_rate: Optional[float] = None
    quality_score: Optional[float] = None
    drift_score: Optional[float] = None
    availability: Optional[float] = None
    last_successful_inference_at: Optional[datetime] = None
    recorded_at: datetime


class MetricRollup(BaseModel):
    """Simple current-state rollup per (model_version, environment) — the
    shape a monitoring dashboard's summary tiles would consume. Full
    time-bucketed rollups (hourly/daily) are a Postgres-partition-backed
    feature noted in architecture.md Q6 / roadmap.md, out of scope for
    the take-home's SQLite default."""

    model_config = ConfigDict(protected_namespaces=())

    model_version_id: str
    environment: str
    latest: Optional[MetricSnapshotRead] = None
    monitoring_status: str  # HEALTHY | DEGRADED | NO_DATA
