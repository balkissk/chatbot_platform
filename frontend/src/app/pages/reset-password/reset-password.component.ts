import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { LucideEye, LucideEyeOff, LucideLockKeyhole } from '@lucide/angular';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-reset-password',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideEye, LucideEyeOff, LucideLockKeyhole],
  templateUrl: './reset-password.component.html',
  styleUrls: ['../login/login.component.css']
})
export class ResetPasswordComponent {
  token = '';
  password = '';
  confirmPassword = '';
  showPassword = signal(false);
  showConfirmPassword = signal(false);
  submitted = signal(false);
  error = signal('');
  message = signal('');
  loading = signal(false);
  resetComplete = signal(false);

  constructor(
    private auth: AuthService,
    route: ActivatedRoute
  ) {
    this.token = route.snapshot.queryParamMap.get('token') || '';
    if (!this.token) {
      this.error.set('Invalid or missing reset token.');
    }
  }

  submit() {
    this.submitted.set(true);
    if (
      !this.token ||
      this.loading() ||
      !this.password ||
      !this.confirmPassword ||
      this.passwordPolicyError() ||
      this.passwordMismatch()
    ) {
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.message.set('');
    this.resetComplete.set(false);

    this.auth.resetPassword(this.token, this.password).subscribe({
      next: response => {
        this.message.set(response.message);
        this.password = '';
        this.confirmPassword = '';
        this.resetComplete.set(true);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not reset password');
        this.loading.set(false);
      }
    });
  }

  passwordMismatch() {
    return Boolean(this.confirmPassword && this.password && this.confirmPassword !== this.password);
  }

  passwordPolicyError() {
    if (!this.password) return '';
    if (this.password.length < 8) return 'Password must be at least 8 characters.';
    if (!/[A-Z]/.test(this.password)) return 'Password must include at least one uppercase letter.';
    if (!/[a-z]/.test(this.password)) return 'Password must include at least one lowercase letter.';
    if (!/\d/.test(this.password)) return 'Password must include at least one number.';
    return '';
  }

  togglePasswordVisibility() {
    this.showPassword.update(show => !show);
  }

  toggleConfirmPasswordVisibility() {
    this.showConfirmPassword.update(show => !show);
  }
}
