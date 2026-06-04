import { CommonModule } from '@angular/common';
import { isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { apiBaseUrl } from '../../config/app-config';

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-users.component.html',
  styleUrls: ['./admin-users.component.css']
})
export class AdminUsersComponent implements OnInit {
  users = signal<any[]>([]);
  loading = signal(false);
  error = signal('');
  createError = signal('');
  creating = signal(false);
  actionId = signal<number | undefined>(undefined);

  search = '';
  roleFilter = '';
  statusFilter = '';
  newUser = {
    name: '',
    email: '',
    password: '',
    role: 'manager'
  };
  private isBrowser: boolean;
  private baseUrl = apiBaseUrl();

  constructor(
    private http: HttpClient,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.loadUsers();
  }

  loadUsers() {
    if (!this.isBrowser) return;

    this.loading.set(true);
    this.error.set('');

    const params: any = {};
    if (this.search.trim()) params.search = this.search.trim();
    if (this.roleFilter) params.role = this.roleFilter;
    if (this.statusFilter) params.status = this.statusFilter;

    this.http.get<any[]>(`${this.baseUrl}/auth/users`, { params }).subscribe({
      next: users => {
        this.users.set(users);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load users');
        this.loading.set(false);
      }
    });
  }

  createUser() {
    if (!this.newUser.name.trim() || !this.newUser.email.trim() || !this.newUser.password.trim()) {
      this.createError.set('Name, email, and password are required');
      return;
    }

    this.creating.set(true);
    this.createError.set('');

    this.http.post<any>(`${this.baseUrl}/auth/users`, {
      name: this.newUser.name.trim(),
      email: this.newUser.email.trim(),
      password: this.newUser.password,
      role: this.newUser.role
    }).subscribe({
      next: () => {
        this.newUser = {
          name: '',
          email: '',
          password: '',
          role: 'manager'
        };
        this.creating.set(false);
        this.loadUsers();
      },
      error: err => {
        this.createError.set(err.error?.detail || 'Could not create user');
        this.creating.set(false);
      }
    });
  }

  setStatus(user: any, status: 'active' | 'disabled') {
    this.actionId.set(user.id);
    this.error.set('');

    this.http.put<any>(`${this.baseUrl}/auth/users/${user.id}/status`, {
      status
    }).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.loadUsers();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update user status');
        this.actionId.set(undefined);
      }
    });
  }

  updateSearch(value: string) {
    this.search = value;
    this.loadUsers();
  }

  updateRoleFilter(value: string) {
    this.roleFilter = value;
    this.loadUsers();
  }

  updateStatusFilter(value: string) {
    this.statusFilter = value;
    this.loadUsers();
  }

  resetFilters() {
    this.search = '';
    this.roleFilter = '';
    this.statusFilter = '';
    this.loadUsers();
  }
}
