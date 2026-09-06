import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import DomainError, domain_error_handler
from app.core.middleware import CorrelationIdMiddleware
from app.db import AsyncSessionLocal
from app.logging_conf import configure_logging, get_logger
from app.models.model import LifecycleStage, ModelVersion
from app.routers import auth, deployments, health, models
from app.services.deployment_worker import reconcile_stuck_deployments
from sqlalchemy import select

logger = get_logger("app.background")

_METRIC_AGGREGATION_INTERVAL_SECONDS = 30
_RECONCILIATION_INTERVAL_SECONDS = 60


async def _periodic_metric_aggregation() -> None:
    """Long-running async workflow #2 (deployment execution is #1):
    refreshes a metric snapshot for every model version currently in
    PRODUCTION, standing in for a real metrics-scraping pipeline. This is
    exactly the kind of periodic job that moves to Celery beat / a
    scheduled Lambda once real traffic volume exists (roadmap.md)."""
    from app.services.monitoring_service import MonitoringService

    while True:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ModelVersion).where(
                        ModelVersion.lifecycle_stage == LifecycleStage.PRODUCTION
                    )
                )
                monitoring = MonitoringService(session)
                for version in result.scalars().all():
                    await monitoring.simulate_snapshot(version.id, "PRODUCTION")
        except Exception:  # noqa: BLE001 - a background loop must not die
            logger.exception("metric_aggregation.iteration_failed")
        await asyncio.sleep(_METRIC_AGGREGATION_INTERVAL_SECONDS)


async def _periodic_reconciliation() -> None:
    """architecture.md Q3: periodically sweeps for deployments stuck in
    DEPLOYING (worker crashed mid-flight) and heals them against the
    runtime's own view."""
    while True:
        await asyncio.sleep(_RECONCILIATION_INTERVAL_SECONDS)
        try:
            healed = await reconcile_stuck_deployments()
            if healed:
                logger.info("reconciliation.healed count=%d ids=%s", len(healed), healed)
        except Exception:  # noqa: BLE001
            logger.exception("reconciliation.iteration_failed")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.background_tasks = [
        asyncio.create_task(_periodic_metric_aggregation()),
        asyncio.create_task(_periodic_reconciliation()),
    ]
    yield
    for task in app.state.background_tasks:
        task.cancel()


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "MLOps platform API — model registry, deployment lifecycle, "
            "and monitoring for models running across plants/environments."
        ),
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-Id"],
    )
    app.add_middleware(CorrelationIdMiddleware)

    app.add_exception_handler(DomainError, domain_error_handler)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(models.router)
    app.include_router(deployments.router)

    return app


app = create_app()
