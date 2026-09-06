import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ApiService } from './api.service';
import { environment } from '../../../environments/environment';

describe('ApiService', () => {
  let service: ApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ApiService],
    });
    service = TestBed.inject(ApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('builds the request against the configured base URL', () => {
    service.get('/models').subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/models`);
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('omits undefined/empty query params instead of sending them as literal "undefined"', () => {
    service.get('/deployments', { environment: 'PRODUCTION', status: undefined, search: '' }).subscribe();
    const req = httpMock.expectOne(
      (r) => r.url === `${environment.apiBaseUrl}/deployments`
    );
    expect(req.request.params.get('environment')).toBe('PRODUCTION');
    expect(req.request.params.has('status')).toBeFalse();
    expect(req.request.params.has('search')).toBeFalse();
    req.flush([]);
  });
});
