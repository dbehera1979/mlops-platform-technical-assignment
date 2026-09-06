// Mirrors backend/app/schemas/deployment.py

export type DeploymentStatus =
  | 'REQUESTED'
  | 'VALIDATING'
  | 'DEPLOYING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'ROLLED_BACK';

export type FailureClass = 'TRANSIENT' | 'TERMINAL';

export const TERMINAL_STATUSES: DeploymentStatus[] = ['SUCCEEDED', 'FAILED', 'ROLLED_BACK'];

export interface DeploymentEvent {
  id: string;
  from_status?: string | null;
  to_status: string;
  message?: string | null;
  correlation_id?: string | null;
  reconciled: boolean;
  created_at: string;
}

export interface Deployment {
  id: string;
  model_version_id: string;
  environment: string;
  status: DeploymentStatus;
  idempotency_key: string;
  requested_by?: string | null;
  current_attempt: number;
  previous_deployment_id?: string | null;
  failure_reason?: string | null;
  failure_class?: FailureClass | null;
  is_rollback: boolean;
  created_at: string;
  updated_at: string;
  events: DeploymentEvent[];
}

export interface DeploymentCreateRequest {
  model_version_id: string;
  environment: string;
  idempotency_key: string;
  requested_by?: string | null;
  simulate_failure?: boolean | null;
}
