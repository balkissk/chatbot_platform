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
  access_token: string;
  token_type: string;
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
  private tokenKey = 'chatbot_factory_token';
  private userKey = 'chatbot_factory_user';

  currentUser = signal<AuthUser | null>(this.readStoredUser());

  constructor(
    private http: HttpClient,
    private router: Router
  ) {}

  get token() {
    const storage = this.safeLocalStorage();
    return storage?.getItem(this.tokenKey) ?? null;
  }

  get isAuthenticated() {
    this.restoreSession();
    return !!this.token && !!this.currentUser();
  }

  login(email: string, password: string) {
    return this.http.post<AuthResponse>(`${this.baseUrl}/auth/login`, {
      email,
      password
    });
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
    return this.http.post<MessageResponse>(`${this.baseUrl}/auth/forgot-password`, { email });
  }

  resetPassword(token: string, newPassword: string) {
    return this.http.post<MessageResponse>(`${this.baseUrl}/auth/reset-password`, {
      token,
      new_password: newPassword
    });
  }

  saveSession(response: AuthResponse) {
    const storage = this.safeLocalStorage();
    if (!storage) return;
    storage.setItem(this.tokenKey, response.access_token);
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
    const storage = this.safeLocalStorage();
    if (storage) {
      storage.removeItem(this.tokenKey);
      storage.removeItem(this.userKey);
    }
    this.currentUser.set(null);
    this.router.navigate(['/login']);
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
      return;
    }

    const token = this.token;
    if (!token) return;

    const user = this.readUserFromToken(token);
    if (user) {
      storage.setItem(this.userKey, JSON.stringify(user));
      this.currentUser.set(user);
    }
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

  private readUserFromToken(token: string): AuthUser | null {
    try {
      const payloadValue = token.split('.')[1];
      const base64 = payloadValue.replace(/-/g, '+').replace(/_/g, '/');
      const paddedBase64 = base64.padEnd(base64.length + (-base64.length % 4), '=');
      const payload = JSON.parse(atob(paddedBase64));
      if (!payload?.sub || !payload?.email || !payload?.role) return null;
      if (!['admin', 'manager', 'end_user'].includes(payload.role)) return null;

      return {
        id: Number(payload.sub),
        name: payload.email,
        email: payload.email,
        role: payload.role as AuthUser['role'],
        status: 'active'
      };
    } catch {
      return null;
    }
  }
}
