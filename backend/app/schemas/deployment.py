from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.deployment import DeploymentStatus, FailureClass


class DeploymentCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version_id: str
    environment: str = Field(min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=1, max_length=200)
    requested_by: Optional[str] = None
    # Demo/test-only: force a deterministic outcome instead of the
    # runtime's randomized failure simulation. True=succeed, False=fail,
    # omitted=random. Never used by a real caller in production.
    simulate_failure: Optional[bool] = None


class DeploymentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    from_status: Optional[str] = None
    to_status: str
    message: Optional[str] = None
    correlation_id: Optional[str] = None
    reconciled: bool = False
    created_at: datetime


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    model_version_id: str
    environment: str
    status: DeploymentStatus
    idempotency_key: str
    requested_by: Optional[str] = None
    current_attempt: int
    previous_deployment_id: Optional[str] = None
    failure_reason: Optional[str] = None
    failure_class: Optional[FailureClass] = None
    is_rollback: bool
    created_at: datetime
    updated_at: datetime
    events: list[DeploymentEventRead] = []
