import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { apiBaseUrl } from '../config/app-config';

export interface AuthUser {
  id: number;
  name: string;
  email: string;
  role: 'admin' | 'manager' | 'end_user';
  status: string;
}

interface AuthResponse {
  user: AuthUser;
}

interface RegisterResponse {
  message: string;
  user: AuthUser;
}

interface MessageResponse {
  message: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private baseUrl = apiBaseUrl();
  private userKey = 'chatbot_factory_user';

  currentUser = signal<AuthUser | null>(this.readStoredUser());

  constructor(
    private http: HttpClient,
    private router: Router
  ) {}

  get isAuthenticated() {
    this.restoreSession();
    return !!this.currentUser();
  }

  login(email: string, password: string) {
    return this.http.post<AuthResponse>(
      `${this.baseUrl}/auth/login`,
      { email, password },
      { withCredentials: true }
    );
  }

  register(name: string, email: string, password: string, role: string) {
    return this.http.post<RegisterResponse>(`${this.baseUrl}/auth/register`, {
      name,
      email,
      password,
      role
    });
  }

  forgotPassword(email: string) {
    return this.http.post<MessageResponse>(
      `${this.baseUrl}/auth/forgot-password`,
      { email },
      { withCredentials: true }
    );
  }

  resetPassword(token: string, newPassword: string) {
    return this.http.post<MessageResponse>(
      `${this.baseUrl}/auth/reset-password`,
      { token, new_password: newPassword },
      { withCredentials: true }
    );
  }

  saveSession(response: AuthResponse) {
    const storage = this.safeLocalStorage();
    if (!storage) return;
    storage.setItem(this.userKey, JSON.stringify(response.user));
    this.currentUser.set(response.user);
  }

  updateStoredUser(user: AuthUser) {
    const storage = this.safeLocalStorage();
    if (storage) {
      storage.setItem(this.userKey, JSON.stringify(user));
    }
    this.currentUser.set(user);
  }

  logout() {
    this.http.post<MessageResponse>(`${this.baseUrl}/auth/logout`, {}, { withCredentials: true }).subscribe({
      next: () => this.clearLocalSession(),
      error: () => this.clearLocalSession()
    });
  }

  expireSession() {
    const storage = this.safeLocalStorage();
    if (storage) {
      storage.removeItem(this.userKey);
      storage.removeItem('chatbot_factory_token');
      storage.setItem('chatbot_factory_session_message', 'Your session has expired. Please sign in again.');
    }
    this.currentUser.set(null);
    if (this.router.url !== '/login') {
      this.router.navigate(['/login']);
    }
  }

  consumeSessionMessage() {
    const storage = this.safeLocalStorage();
    if (!storage) return '';

    const message = storage.getItem('chatbot_factory_session_message') || '';
    storage.removeItem('chatbot_factory_session_message');
    return message;
  }

  hasRole(roles: string[]) {
    this.restoreSession();
    const user = this.currentUser();
    return !!user && roles.includes(user.role);
  }

  homeForRole(role: string) {
    if (role === 'admin') return '/admin/users';
    if (role === 'manager') return '/dashboard/projects';
    return '/chat/3';
  }

  private readStoredUser(): AuthUser | null {
    const storage = this.safeLocalStorage();
    if (!storage) return null;
    const rawUser = storage.getItem(this.userKey);
    if (!rawUser) return null;

    try {
      return JSON.parse(rawUser);
    } catch {
      storage.removeItem(this.userKey);
      return null;
    }
  }

  private restoreSession() {
    const storage = this.safeLocalStorage();
    if (!storage || this.currentUser()) return;

    const storedUser = this.readStoredUser();
    if (storedUser) {
      this.currentUser.set(storedUser);
    }
  }

  private clearLocalSession() {
    const storage = this.safeLocalStorage();
    if (storage) {
      storage.removeItem(this.userKey);
      storage.removeItem('chatbot_factory_token');
    }
    this.currentUser.set(null);
    this.router.navigate(['/login']);
  }

  private safeLocalStorage(): Storage | null {
    if (typeof localStorage === 'undefined') return null;
    if (
      typeof localStorage.getItem !== 'function' ||
      typeof localStorage.setItem !== 'function' ||
      typeof localStorage.removeItem !== 'function'
    ) {
      return null;
    }
    return localStorage;
  }

}
