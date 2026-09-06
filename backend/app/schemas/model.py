from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.model import ApprovalDecision, LifecycleStage


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    owner_team: Optional[str] = None


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    name: str
    description: Optional[str] = None
    owner_team: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ModelVersionCreate(BaseModel):
    version_label: str = Field(min_length=1, max_length=50)
    framework: str
    algorithm: str
    artifact_uri: str
    training_data_ref: Optional[str] = None
    tags: dict = Field(default_factory=dict)
    created_by: Optional[str] = None


class ModelVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    model_id: str
    version_label: str
    framework: str
    algorithm: str
    artifact_uri: str
    training_data_ref: Optional[str] = None
    tags: dict
    lifecycle_stage: LifecycleStage
    created_by: Optional[str] = None
    row_version: int
    created_at: datetime
    updated_at: datetime


class PromotionRequest(BaseModel):
    """expected_row_version implements the optimistic-concurrency check
    described in architecture.md Q2: caller must supply the version it
    last read, or the promotion is rejected with 409."""

    to_stage: LifecycleStage
    approved_by: str
    decision: ApprovalDecision = ApprovalDecision.APPROVED
    reason: Optional[str] = None
    expected_row_version: int


class ApprovalRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    model_version_id: str
    from_stage: LifecycleStage
    to_stage: LifecycleStage
    approved_by: str
    decision: ApprovalDecision
    reason: Optional[str] = None
    created_at: datetime
