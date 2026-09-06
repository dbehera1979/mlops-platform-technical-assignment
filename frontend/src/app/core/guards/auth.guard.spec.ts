import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { authGuard } from './auth.guard';
import { AuthService } from '../services/auth.service';

describe('authGuard', () => {
  let router: Router;
  let mockAuth: { snapshot: unknown };

  beforeEach(() => {
    mockAuth = { snapshot: null };
    TestBed.configureTestingModule({
      imports: [RouterTestingModule],
      providers: [{ provide: AuthService, useValue: mockAuth }],
    });
    router = TestBed.inject(Router);
  });

  function runGuard(): boolean {
    return TestBed.runInInjectionContext(() => authGuard({} as never, {} as never)) as boolean;
  }

  it('allows navigation when a user is signed in', () => {
    mockAuth.snapshot = { username: 'operator', roles: ['operator'] };
    expect(runGuard()).toBeTrue();
  });

  it('redirects to /login and blocks navigation when no user is signed in', () => {
    const navigateSpy = spyOn(router, 'navigate');
    mockAuth.snapshot = null;
    expect(runGuard()).toBeFalse();
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });
});
