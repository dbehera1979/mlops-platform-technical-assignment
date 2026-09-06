import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CurrentUser, DemoRole, TokenResponse } from '../models/auth.model';

const STORAGE_KEY = 'mlops.auth';

/** Demo/take-home auth (see backend app/core/security.py docstring):
 * username IS the role, password is ignored. Real deployments swap this
 * for OIDC/SSO without changing AuthGuard or the interceptor. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly currentUserSubject = new BehaviorSubject<CurrentUser | null>(this.restore());
  readonly currentUser$: Observable<CurrentUser | null> = this.currentUserSubject.asObservable();

  constructor(private readonly http: HttpClient) {}

  get token(): string | null {
    return this.currentUserSubject.value ? this.readToken() : null;
  }

  get snapshot(): CurrentUser | null {
    return this.currentUserSubject.value;
  }

  hasRole(...roles: DemoRole[]): boolean {
    const user = this.currentUserSubject.value;
    return !!user && roles.some((r) => user.roles.includes(r));
  }

  loginAs(username: DemoRole): Observable<TokenResponse> {
    const body = new URLSearchParams();
    body.set('username', username);
    body.set('password', 'demo');
    return this.http
      .post<TokenResponse>(`${environment.apiBaseUrl}/auth/token`, body.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      .pipe(
        tap((res) => {
          const user: CurrentUser = { username, roles: [username] };
          localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, token: res.access_token }));
          this.currentUserSubject.next(user);
        })
      );
  }

  logout(): void {
    localStorage.removeItem(STORAGE_KEY);
    this.currentUserSubject.next(null);
  }

  private readToken(): string | null {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw).token ?? null;
    } catch {
      return null;
    }
  }

  private restore(): CurrentUser | null {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw).user ?? null;
    } catch {
      return null;
    }
  }
}
