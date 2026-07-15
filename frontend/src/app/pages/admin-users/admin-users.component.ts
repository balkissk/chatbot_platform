import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { apiBaseUrl } from '../../config/app-config';

type UserStatus = 'active' | 'disabled';

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-users.component.html',
  styleUrls: ['./admin-users.component.css']
})
export class AdminUsersComponent implements OnInit {
  users = signal<any[]>([]);
  stats = signal({ total_users: 0, active_users: 0, disabled_users: 0, managers: 0 });
  loading = signal(false);
  error = signal('');
  createError = signal('');
  creating = signal(false);
  actionId = signal<number | undefined>(undefined);
  addModalOpen = signal(false);
  formSubmitted = signal(false);
  selectedUser = signal<any | null>(null);
  confirmAction = signal<{ user: any; status: UserStatus } | null>(null);
  openMenuId = signal<number | undefined>(undefined);

  search = '';
  roleFilter = '';
  statusFilter = '';
  currentPage = 1;
  pageSize = 10;
  totalUsersCount = 0;
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
    this.openMenuId.set(undefined);

    const params: any = {};
    if (this.search.trim()) params.search = this.search.trim();
    if (this.roleFilter) params.role = this.roleFilter;
    if (this.statusFilter) params.status = this.statusFilter;
    params.page = this.currentPage;
    params.page_size = this.pageSize;

    this.http.get<any>(`${this.baseUrl}/auth/users`, { params }).subscribe({
      next: response => {
        this.users.set(response.items || []);
        this.totalUsersCount = Number(response.total || 0);
        if (response.page) this.currentPage = Number(response.page);
        if (response.page_size) this.pageSize = Number(response.page_size);
        if (response.stats) this.stats.set(response.stats);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load users');
        this.loading.set(false);
      }
    });
  }

  openAddUserModal() {
    this.createError.set('');
    this.formSubmitted.set(false);
    this.addModalOpen.set(true);
  }

  closeAddUserModal() {
    if (this.creating()) return;
    this.addModalOpen.set(false);
    this.createError.set('');
    this.formSubmitted.set(false);
  }

  createUser() {
    this.formSubmitted.set(true);
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
        this.resetNewUser();
        this.creating.set(false);
        this.addModalOpen.set(false);
        this.formSubmitted.set(false);
        this.loadUsers();
      },
      error: err => {
        this.createError.set(err.error?.detail || 'Could not create user');
        this.creating.set(false);
      }
    });
  }

  askStatusChange(user: any, status: UserStatus) {
    this.openMenuId.set(undefined);
    this.confirmAction.set({ user, status });
  }

  closeConfirmation() {
    if (this.actionId()) return;
    this.confirmAction.set(null);
  }

  confirmStatusChange() {
    const action = this.confirmAction();
    if (!action) return;
    this.setStatus(action.user, action.status);
  }

  setStatus(user: any, status: UserStatus) {
    this.actionId.set(user.id);
    this.error.set('');

    this.http.put<any>(`${this.baseUrl}/auth/users/${user.id}/status`, {
      status
    }).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.confirmAction.set(null);
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
  }

  updateRoleFilter(value: string) {
    this.roleFilter = value;
  }

  updateStatusFilter(value: string) {
    this.statusFilter = value;
  }

  resetFilters() {
    this.search = '';
    this.roleFilter = '';
    this.statusFilter = '';
    this.currentPage = 1;
    this.loadUsers();
  }

  applyFilters() {
    this.currentPage = 1;
    this.loadUsers();
  }

  toggleMenu(user: any) {
    this.openMenuId.set(this.openMenuId() === user.id ? undefined : user.id);
  }

  openDetails(user: any) {
    this.openMenuId.set(undefined);
    this.selectedUser.set(user);
  }

  closeDetails() {
    this.selectedUser.set(null);
  }

  totalUsers() {
    return this.stats().total_users;
  }

  activeUsers() {
    return this.stats().active_users;
  }

  disabledUsers() {
    return this.stats().disabled_users;
  }

  managers() {
    return this.stats().managers;
  }

  totalPages() {
    return Math.max(1, Math.ceil(this.totalUsersCount / this.pageSize));
  }

  pagedUsers() {
    return this.users();
  }

  rangeStart() {
    return this.totalUsersCount ? (this.currentPage - 1) * this.pageSize + 1 : 0;
  }

  rangeEnd() {
    return Math.min(this.currentPage * this.pageSize, this.totalUsersCount);
  }

  previousPage() {
    this.currentPage = Math.max(1, this.currentPage - 1);
    this.loadUsers();
  }

  nextPage() {
    this.currentPage = Math.min(this.totalPages(), this.currentPage + 1);
    this.loadUsers();
  }

  roleLabel(role: string) {
    const labels: Record<string, string> = {
      admin: 'Admin',
      manager: 'Manager',
      end_user: 'End User'
    };
    return labels[role] || role || 'Unknown';
  }

  statusLabel(status: string) {
    return status === 'disabled' ? 'Disabled' : 'Active';
  }

  lastLoginLabel(user: any) {
    return user?.last_login_at ? user.last_login_at : null;
  }

  initials(user: any) {
    const source = user?.name || user?.email || 'U';
    return source
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part: string) => part.charAt(0).toUpperCase())
      .join('') || 'U';
  }

  fieldInvalid(field: 'name' | 'email' | 'password') {
    return this.formSubmitted() && !String(this.newUser[field] || '').trim();
  }

  confirmTitle() {
    return this.confirmAction()?.status === 'disabled' ? 'Disable this user?' : 'Activate this user?';
  }

  confirmMessage() {
    return this.confirmAction()?.status === 'disabled'
      ? 'This user will no longer be able to sign in.'
      : 'This user will regain access to the platform.';
  }

  private resetNewUser() {
    this.newUser = {
      name: '',
      email: '',
      password: '',
      role: 'manager'
    };
  }
}
