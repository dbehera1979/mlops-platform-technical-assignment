import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

/** Thin, single choke point for every HTTP call the app makes — no
 * feature component or service ever imports HttpClient directly. This is
 * the seam that keeps Angular isolated from backend internals
 * (architecture.md Q9): a backend refactor is invisible here as long as
 * the JSON contract holds, and swapping API host/auth/tracing is a
 * one-file change. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly base = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Observable<T> {
    return this.http.get<T>(`${this.base}${path}`, { params: this.toHttpParams(params) });
  }

  post<T>(path: string, body: unknown, params?: Record<string, string | number | boolean | undefined>): Observable<T> {
    return this.http.post<T>(`${this.base}${path}`, body, { params: this.toHttpParams(params) });
  }

  private toHttpParams(params?: Record<string, string | number | boolean | undefined>): HttpParams {
    let httpParams = new HttpParams();
    if (!params) return httpParams;
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        httpParams = httpParams.set(key, String(value));
      }
    }
    return httpParams;
  }
}
