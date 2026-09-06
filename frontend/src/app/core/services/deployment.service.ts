import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, firstValueFrom } from 'rxjs';
import { ApiError } from '../models/api-error.model';
import { Deployment, DeploymentCreateRequest } from '../models/deployment.model';
import { RemoteData, failure, loading, success } from '../models/remote-data.model';
import { ApiService } from './api.service';

export interface DeploymentFilters {
  model_version_id?: string;
  environment?: string;
  status?: string;
}

/** RxJS-backed store for Deployments. Deployment execution is
 * asynchronous on the backend (ADR-001) — `requestDeployment` returns as
 * soon as the backend accepts the request (202/REQUESTED), and this
 * service's `poll()` is what the UI uses to watch a deployment move
 * through VALIDATING -> DEPLOYING -> a terminal state without the user
 * refreshing the page. */
@Injectable({ providedIn: 'root' })
export class DeploymentService {
  private readonly listSubject = new BehaviorSubject<RemoteData<Deployment[]>>({ status: 'idle' });
  readonly list$: Observable<RemoteData<Deployment[]>> = this.listSubject.asObservable();

  constructor(private readonly api: ApiService) {}

  async loadDeployments(filters: DeploymentFilters = {}): Promise<void> {
    this.listSubject.next(loading());
    try {
      const deployments = await firstValueFrom(
        this.api.get<Deployment[]>('/deployments', { ...filters })
      );
      this.listSubject.next(success(deployments));
    } catch (err) {
      this.listSubject.next(failure(err as ApiError));
    }
  }

  async getDeployment(id: string): Promise<Deployment> {
    return firstValueFrom(this.api.get<Deployment>(`/deployments/${id}`));
  }

  async requestDeployment(payload: DeploymentCreateRequest): Promise<Deployment> {
    return firstValueFrom(this.api.post<Deployment>('/deployments', payload));
  }

  async retry(deploymentId: string, simulateFailure?: boolean): Promise<Deployment> {
    return firstValueFrom(
      this.api.post<Deployment>(`/deployments/${deploymentId}/retry`, {}, { simulate_failure: simulateFailure })
    );
  }

  async rollback(deploymentId: string): Promise<Deployment> {
    return firstValueFrom(this.api.post<Deployment>(`/deployments/${deploymentId}/rollback`, {}));
  }

  /** Polls a deployment until it reaches a terminal status or the
   * attempt budget runs out — backs the "watch it finish" UX for a
   * just-triggered deployment/retry/rollback in the Deployment view. */
  async pollUntilTerminal(id: string, { intervalMs = 700, maxAttempts = 15 } = {}): Promise<Deployment> {
    const terminal = new Set(['SUCCEEDED', 'FAILED', 'ROLLED_BACK']);
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const deployment = await this.getDeployment(id);
      if (terminal.has(deployment.status)) return deployment;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    return this.getDeployment(id);
  }
}
