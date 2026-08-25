import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { vi } from 'vitest';

import { AuthService } from './auth';

describe('AuthService session expiration', () => {
  let navigate: ReturnType<typeof vi.fn>;
  let auth: AuthService;

  beforeEach(() => {
    navigate = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        {
          provide: Router,
          useValue: {
            url: '/dashboard/projects',
            navigate
          }
        }
      ]
    });
    auth = TestBed.inject(AuthService);
    localStorage.setItem('chatbot_factory_token', 'expired-token');
    localStorage.setItem('chatbot_factory_user', '{"email":"user@example.com"}');
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('cleans local session and redirects to login on expiration', () => {
    auth.expireSession();

    expect(localStorage.getItem('chatbot_factory_token')).toBeNull();
    expect(localStorage.getItem('chatbot_factory_user')).toBeNull();
    expect(localStorage.getItem('chatbot_factory_session_message')).toBe('Your session has expired. Please sign in again.');
    expect(navigate).toHaveBeenCalledWith(['/login']);
  });

  it('does not redirect again when already on login', () => {
    const router = TestBed.inject(Router) as unknown as { url: string };
    router.url = '/login';

    auth.expireSession();

    expect(navigate).not.toHaveBeenCalled();
  });

  it('exposes the session expiration message once', () => {
    auth.expireSession();

    expect(auth.consumeSessionMessage()).toBe('Your session has expired. Please sign in again.');
    expect(auth.consumeSessionMessage()).toBe('');
  });
});
