import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, firstValueFrom } from 'rxjs';
import { ApiError } from '../models/api-error.model';
import { ModelMetricsResponse } from '../models/metrics.model';
import { RemoteData, failure, loading, success } from '../models/remote-data.model';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class MonitoringService {
  private readonly metricsSubject = new BehaviorSubject<Map<string, RemoteData<ModelMetricsResponse>>>(new Map());
  readonly metricsByModel$: Observable<Map<string, RemoteData<ModelMetricsResponse>>> = this.metricsSubject.asObservable();

  constructor(private readonly api: ApiService) {}

  async loadMetrics(modelId: string): Promise<void> {
    this.patch(modelId, loading());
    try {
      const metrics = await firstValueFrom(this.api.get<ModelMetricsResponse>(`/models/${modelId}/metrics`));
      this.patch(modelId, success(metrics));
    } catch (err) {
      this.patch(modelId, failure(err as ApiError));
    }
  }

  private patch(modelId: string, state: RemoteData<ModelMetricsResponse>): void {
    const next = new Map(this.metricsSubject.value);
    next.set(modelId, state);
    this.metricsSubject.next(next);
  }
}
