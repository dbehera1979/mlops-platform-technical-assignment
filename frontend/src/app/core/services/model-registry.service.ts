import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, firstValueFrom } from 'rxjs';
import { ApiError } from '../models/api-error.model';
import {
  ModelCreateRequest,
  ModelSummary,
  ModelVersion,
  ModelVersionCreateRequest,
  PromotionRequest,
} from '../models/model.model';
import { RemoteData, failure, loading, success } from '../models/remote-data.model';
import { ApiService } from './api.service';

/** RxJS-backed store for the Model Registry feature. Model Inventory and
 * Model Version Detail both read `models$`/`versionsByModel$` rather than
 * calling the API directly — this is the "RxJS state" layer the UI is
 * built on, and it's what lets the inventory list and a version-detail
 * page share the same in-memory model list without re-fetching. */
@Injectable({ providedIn: 'root' })
export class ModelRegistryService {
  private readonly modelsSubject = new BehaviorSubject<RemoteData<ModelSummary[]>>({ status: 'idle' });
  readonly models$: Observable<RemoteData<ModelSummary[]>> = this.modelsSubject.asObservable();

  private readonly versionsSubject = new BehaviorSubject<Map<string, RemoteData<ModelVersion[]>>>(new Map());
  readonly versionsByModel$: Observable<Map<string, RemoteData<ModelVersion[]>>> = this.versionsSubject.asObservable();

  constructor(private readonly api: ApiService) {}

  async loadModels(search?: string): Promise<void> {
    this.modelsSubject.next(loading());
    try {
      const models = await firstValueFrom(this.api.get<ModelSummary[]>('/models', { search }));
      this.modelsSubject.next(success(models));
    } catch (err) {
      this.modelsSubject.next(failure(err as ApiError));
    }
  }

  async getModel(modelId: string): Promise<ModelSummary> {
    return firstValueFrom(this.api.get<ModelSummary>(`/models/${modelId}`));
  }

  async createModel(payload: ModelCreateRequest): Promise<ModelSummary> {
    const model = await firstValueFrom(this.api.post<ModelSummary>('/models', payload));
    await this.loadModels();
    return model;
  }

  async loadVersions(modelId: string): Promise<void> {
    this.patchVersions(modelId, loading());
    try {
      const versions = await firstValueFrom(this.api.get<ModelVersion[]>(`/models/${modelId}/versions`));
      this.patchVersions(modelId, success(versions));
    } catch (err) {
      this.patchVersions(modelId, failure(err as ApiError));
    }
  }

  async registerVersion(modelId: string, payload: ModelVersionCreateRequest): Promise<ModelVersion> {
    const version = await firstValueFrom(
      this.api.post<ModelVersion>(`/models/${modelId}/versions`, payload)
    );
    await this.loadVersions(modelId);
    return version;
  }

  async promoteVersion(modelId: string, versionId: string, payload: PromotionRequest): Promise<ModelVersion> {
    const version = await firstValueFrom(
      this.api.post<ModelVersion>(`/models/versions/${versionId}/promote`, payload)
    );
    await this.loadVersions(modelId);
    return version;
  }

  private patchVersions(modelId: string, state: RemoteData<ModelVersion[]>): void {
    const next = new Map(this.versionsSubject.value);
    next.set(modelId, state);
    this.versionsSubject.next(next);
  }
}
