import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { AuthService, AuthUser } from '../../services/auth';
import { apiBaseUrl } from '../../config/app-config';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './profile.component.html',
  styleUrls: ['./profile.component.css']
})
export class ProfileComponent implements OnInit {
  user = signal<AuthUser | null>(null);
  loading = signal(false);
  savingProfile = signal(false);
  savingPassword = signal(false);
  profileMessage = signal('');
  passwordMessage = signal('');
  error = signal('');
  passwordError = signal('');

  name = '';
  currentPassword = '';
  newPassword = '';
  confirmPassword = '';
  showCurrentPassword = false;
  showNewPassword = false;
  showConfirmPassword = false;

  private baseUrl = apiBaseUrl();
  private isBrowser: boolean;

  constructor(
    private http: HttpClient,
    private auth: AuthService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.loadProfile();
  }

  loadProfile() {
    this.loading.set(true);
    this.error.set('');

    this.http.get<AuthUser>(`${this.baseUrl}/auth/me`).subscribe({
      next: user => {
        this.user.set(user);
        this.name = user.name;
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load profile');
        this.loading.set(false);
      }
    });
  }

  updateProfile() {
    const name = this.name.trim();
    if (!name) {
      this.error.set('Name is required');
      return;
    }
    if (!this.canSaveProfile()) {
      return;
    }

    this.savingProfile.set(true);
    this.error.set('');
    this.profileMessage.set('');

    this.http.put<AuthUser>(`${this.baseUrl}/auth/me`, { name }).subscribe({
      next: user => {
        this.user.set(user);
        this.name = user.name;
        this.auth.updateStoredUser(user);
        this.profileMessage.set('Profile updated');
        this.savingProfile.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update profile');
        this.savingProfile.set(false);
      }
    });
  }

  changePassword() {
    this.passwordError.set('');
    this.passwordMessage.set('');

    if (!this.currentPassword || !this.newPassword || !this.confirmPassword) {
      this.passwordError.set('All password fields are required');
      return;
    }

    if (this.newPassword !== this.confirmPassword) {
      this.passwordError.set('New passwords do not match');
      return;
    }
    if (this.newPassword.length < 8) {
      this.passwordError.set('New password must be at least 8 characters');
      return;
    }
    if (this.savingPassword()) {
      return;
    }

    this.savingPassword.set(true);

    this.http.put(`${this.baseUrl}/auth/me/password`, {
      current_password: this.currentPassword,
      new_password: this.newPassword
    }).subscribe({
      next: () => {
        this.currentPassword = '';
        this.newPassword = '';
        this.confirmPassword = '';
        this.passwordMessage.set('Password updated');
        this.savingPassword.set(false);
      },
      error: err => {
        this.passwordError.set(err.error?.detail || 'Could not update password');
        this.savingPassword.set(false);
      }
    });
  }

  roleLabel(role: string) {
    if (role === 'admin') return 'Platform Admin';
    if (role === 'manager') return 'Manager';
    if (role === 'end_user') return 'End User';
    return role;
  }

  statusLabel(status: string) {
    if (!status) return 'Unknown';
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  trimmedName() {
    return this.name.trim();
  }

  nameInvalid() {
    const name = this.trimmedName();
    return !name || name.length > 120;
  }

  profileChanged() {
    const currentUser = this.user();
    return !!currentUser && this.trimmedName() !== currentUser.name;
  }

  canSaveProfile() {
    return !this.loading() && !this.savingProfile() && !this.nameInvalid() && this.profileChanged();
  }

  passwordInvalid() {
    return (
      !this.currentPassword ||
      !this.newPassword ||
      !this.confirmPassword ||
      this.newPassword.length < 8 ||
      this.newPassword !== this.confirmPassword
    );
  }

  canChangePassword() {
    return !this.savingPassword() && !this.passwordInvalid();
  }
}
