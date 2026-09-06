"""Monitoring Service: metric ingestion + a simulated generator standing
in for a real metrics pipeline (architecture.md §5/§9, mandatory scope
item "Monitoring"). A production version ingests from the serving
runtime/APM; this take-home generates plausible values so the dashboard
and rollup logic are genuinely exercised end-to-end.
"""
import random
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.metrics import MetricSnapshot
from app.repositories.metrics_repository import MetricsRepository
from app.repositories.model_repository import ModelRepository


# A snapshot is DEGRADED if any of these thresholds are breached — the
# simple rule an operational dashboard's status chip would apply.
DEGRADED_THRESHOLDS = {
    "error_rate": 0.05,
    "drift_score": 0.3,
    "availability_below": 0.99,
}


class MonitoringService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = MetricsRepository(session)
        self.model_repo = ModelRepository(session)

    async def record_snapshot(self, snapshot: MetricSnapshot) -> MetricSnapshot:
        snapshot = await self.repo.add_snapshot(snapshot)
        await self.session.commit()
        return snapshot

    async def simulate_snapshot(
        self, model_version_id: str, environment: str
    ) -> MetricSnapshot:
        """Generates one plausible metric snapshot. Called after a
        successful PRODUCTION deployment and by the periodic aggregator
        (see main.py) for already-live versions."""
        version = await self.model_repo.get_version(model_version_id)
        if not version:
            raise NotFoundError(f"Model version '{model_version_id}' not found")

        error_rate = max(0.0, random.gauss(0.02, 0.015))
        drift_score = max(0.0, min(1.0, random.gauss(0.1, 0.08)))
        availability = min(1.0, max(0.9, random.gauss(0.997, 0.004)))

        snapshot = MetricSnapshot(
            model_version_id=model_version_id,
            environment=environment,
            latency_ms_p50=max(1.0, random.gauss(40, 8)),
            latency_ms_p99=max(1.0, random.gauss(180, 40)),
            throughput_rps=max(0.0, random.gauss(120, 25)),
            error_rate=round(error_rate, 4),
            quality_score=round(min(1.0, max(0.0, random.gauss(0.92, 0.03))), 4),
            drift_score=round(drift_score, 4),
            availability=round(availability, 4),
            last_successful_inference_at=datetime.now(timezone.utc),
        )
        return await self.record_snapshot(snapshot)

    async def get_rollup(self, model_version_id: str, environment: str) -> dict:
        version = await self.model_repo.get_version(model_version_id)
        if not version:
            raise NotFoundError(f"Model version '{model_version_id}' not found")

        latest = await self.repo.latest_snapshot(model_version_id, environment)
        if latest is None:
            status = "NO_DATA"
        else:
            degraded = (
                (latest.error_rate or 0) > DEGRADED_THRESHOLDS["error_rate"]
                or (latest.drift_score or 0) > DEGRADED_THRESHOLDS["drift_score"]
                or (latest.availability or 1) < DEGRADED_THRESHOLDS["availability_below"]
            )
            status = "DEGRADED" if degraded else "HEALTHY"

        return {
            "model_version_id": model_version_id,
            "environment": environment,
            "latest": latest,
            "monitoring_status": status,
        }

    async def get_snapshots_for_model(self, model_id: str) -> list[MetricSnapshot]:
        """Aggregates snapshots across every version of a model — backs
        `GET /models/{model_id}/metrics` per the minimum-API list."""
        versions = await self.model_repo.list_versions(model_id)
        all_snapshots: list[MetricSnapshot] = []
        for version in versions:
            all_snapshots.extend(await self.repo.list_snapshots(version.id, limit=20))
        all_snapshots.sort(key=lambda s: s.recorded_at, reverse=True)
        return all_snapshots
