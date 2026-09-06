"""Pluggable model-runtime abstraction (architecture.md Q4).

The Deployment worker never talks to a specific serving stack directly —
it goes through this interface, so adding a new runtime type (a REST
serving container, a batch-scoring job, a different cloud's endpoint) is
additive: implement `ModelRuntime`, register it in `get_runtime()`, done.

For the take-home, `SimulatedModelRuntime` stands in for a real serving
backend: it has realistic latency and a configurable failure rate so the
full FAILED/retry/rollback machinery is genuinely exercised, not just
theoretically supported.
"""
import asyncio
import random
from dataclasses import dataclass
from typing import Protocol


class RuntimeDeployError(Exception):
    def __init__(self, message: str, *, transient: bool):
        self.message = message
        self.transient = transient
        super().__init__(message)


class ModelRuntime(Protocol):
    async def deploy(self, *, deployment_id: str, model_version_id: str, environment: str) -> None: ...
    async def rollback(self, *, deployment_id: str, model_version_id: str, environment: str) -> None: ...
    async def get_status(self, *, deployment_id: str) -> str: ...


@dataclass
class SimulatedModelRuntime:
    """Deterministic when `force_success` is passed by the caller (used by
    tests and by the `simulate_failure` field on a deployment request);
    otherwise randomized around `failure_rate` for demo realism."""

    min_latency_s: float = 0.02
    max_latency_s: float = 0.08
    failure_rate: float = 0.2
    transient_failure_share: float = 0.7  # of failures, how many are retryable

    async def deploy(
        self,
        *,
        deployment_id: str,
        model_version_id: str,
        environment: str,
        force_success: bool | None = None,
    ) -> None:
        await asyncio.sleep(random.uniform(self.min_latency_s, self.max_latency_s))

        should_fail = (
            (not force_success) if force_success is not None else
            random.random() < self.failure_rate
        )
        if should_fail:
            transient = random.random() < self.transient_failure_share
            reason = (
                "Serving endpoint did not become healthy within timeout"
                if transient
                else "Artifact could not be loaded by the runtime (schema mismatch)"
            )
            raise RuntimeDeployError(reason, transient=transient)

    async def rollback(
        self, *, deployment_id: str, model_version_id: str, environment: str
    ) -> None:
        await asyncio.sleep(random.uniform(self.min_latency_s, self.max_latency_s))
        # Rollback in the simulation is treated as reliably successful once
        # a valid prior deployment exists — the *validity* check happens
        # in DeploymentService before we ever get here.

    async def get_status(self, *, deployment_id: str) -> str:
        """Used by the reconciliation pass (architecture.md Q3) to ask the
        runtime for ground truth when the DB's view is uncertain."""
        return "LIVE"


_default_runtime = SimulatedModelRuntime()


def get_runtime(framework: str | None = None) -> ModelRuntime:
    """Factory keyed by framework/environment in a real implementation
    (architecture.md Q4); every framework maps to the same simulated
    runtime for this take-home."""
    return _default_runtime
