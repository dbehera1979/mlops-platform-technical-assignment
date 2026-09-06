// Mirrors backend/app/schemas/model.py — kept in sync manually for the
// take-home; a real pipeline generates this from the OpenAPI schema in
// CI (see api-design.md) so drift between backend and frontend fails the
// build instead of surfacing as a runtime bug.

export type LifecycleStage =
  | 'DRAFT'
  | 'VALIDATED'
  | 'APPROVED'
  | 'STAGING'
  | 'PRODUCTION'
  | 'ARCHIVED';

export type ApprovalDecision = 'APPROVED' | 'REJECTED';

export interface ModelSummary {
  id: string;
  name: string;
  description?: string | null;
  owner_team?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ModelCreateRequest {
  name: string;
  description?: string | null;
  owner_team?: string | null;
}

export interface ModelVersion {
  id: string;
  model_id: string;
  version_label: string;
  framework: string;
  algorithm: string;
  artifact_uri: string;
  training_data_ref?: string | null;
  tags: Record<string, unknown>;
  lifecycle_stage: LifecycleStage;
  created_by?: string | null;
  row_version: number;
  created_at: string;
  updated_at: string;
}

export interface ModelVersionCreateRequest {
  version_label: string;
  framework: string;
  algorithm: string;
  artifact_uri: string;
  training_data_ref?: string | null;
  tags?: Record<string, unknown>;
  created_by?: string | null;
}

export interface PromotionRequest {
  to_stage: LifecycleStage;
  approved_by: string;
  decision: ApprovalDecision;
  reason?: string | null;
  expected_row_version: number;
}

// The stages a version may move to directly via promotion — mirrors
// ALLOWED_PROMOTIONS in app/models/model.py. PRODUCTION is deliberately
// absent: it's only reached via a successful Deployment.
export const ALLOWED_PROMOTIONS: Record<LifecycleStage, LifecycleStage[]> = {
  DRAFT: ['VALIDATED', 'ARCHIVED'],
  VALIDATED: ['APPROVED', 'ARCHIVED'],
  APPROVED: ['STAGING', 'ARCHIVED'],
  STAGING: ['APPROVED', 'ARCHIVED'],
  PRODUCTION: ['ARCHIVED'],
  ARCHIVED: [],
};
