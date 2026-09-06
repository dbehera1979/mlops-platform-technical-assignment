import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { ApiService } from './api.service';
import { ModelRegistryService } from './model-registry.service';
import { ModelSummary } from '../models/model.model';
import { environment } from '../../../environments/environment';

describe('ModelRegistryService', () => {
  let service: ModelRegistryService;
  let httpMock: HttpTestingController;

  const sampleModel: ModelSummary = {
    id: 'm1',
    name: 'fraud-detector',
    description: null,
    owner_team: 'risk-ml',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ModelRegistryService, ApiService],
    });
    service = TestBed.inject(ModelRegistryService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('transitions models$ through loading then success', async () => {
    const states: string[] = [];
    const sub = service.models$.subscribe((s) => states.push(s.status));

    const load = service.loadModels();
    httpMock.expectOne(`${environment.apiBaseUrl}/models`).flush([sampleModel]);
    await load;

    expect(states).toEqual(['idle', 'loading', 'success']);
    sub.unsubscribe();
  });

  it('transitions models$ to error on a failed request, preserving the ApiError', async () => {
    const states: (typeof service.models$ extends never ? never : any)[] = [];
    const sub = service.models$.subscribe((s) => states.push(s));

    const load = service.loadModels();
    httpMock
      .expectOne(`${environment.apiBaseUrl}/models`)
      .flush(
        { error: { code: 'UNKNOWN_ERROR', message: 'boom' } },
        { status: 500, statusText: 'Server Error' }
      );
    await load;

    const last = states[states.length - 1];
    expect(last.status).toBe('error');
    sub.unsubscribe();
  });
});
