import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse, HttpRequest } from '@angular/common/http';
import { throwError } from 'rxjs';
import { vi } from 'vitest';

import { AuthService } from './auth';
import { authInterceptor } from './auth.interceptor';

describe('authInterceptor', () => {
  let expireSession: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    expireSession = vi.fn();
    localStorage.setItem('chatbot_factory_token', 'expired-token');

    TestBed.configureTestingModule({
      providers: [
        {
          provide: AuthService,
          useValue: { expireSession }
        }
      ]
    });
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('clears the session on expired JWT responses', () => new Promise<void>(resolve => {
    const request = new HttpRequest('GET', '/protected');
    const next = vi.fn().mockReturnValue(
      throwError(() => new HttpErrorResponse({
        status: 401,
        error: { detail: 'Token expired' }
      }))
    );

    TestBed.runInInjectionContext(() => {
      authInterceptor(request, next).subscribe({
        error: () => {
          expect(expireSession).toHaveBeenCalledTimes(1);
          resolve();
        }
      });
    });
  }));
});
