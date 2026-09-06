// Mirrors backend/app/schemas/metrics.py

export interface MetricSnapshot {
  id: string;
  model_version_id: string;
  environment: string;
  latency_ms_p50?: number | null;
  latency_ms_p99?: number | null;
  throughput_rps?: number | null;
  error_rate?: number | null;
  quality_score?: number | null;
  drift_score?: number | null;
  availability?: number | null;
  last_successful_inference_at?: string | null;
  recorded_at: string;
}

export interface ModelMetricsResponse {
  model_id: string;
  snapshots: MetricSnapshot[];
}
