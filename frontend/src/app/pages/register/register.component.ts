import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { LucideEye, LucideEyeOff, LucideLockKeyhole } from '@lucide/angular';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideEye, LucideEyeOff, LucideLockKeyhole],
  templateUrl: './register.component.html',
  styleUrls: ['../login/login.component.css']
})
export class RegisterComponent {
  name = '';
  email = '';
  password = '';
  confirmPassword = '';
  role = 'manager';
  showPassword = signal(false);
  showConfirmPassword = signal(false);
  submitted = signal(false);
  error = signal('');
  message = signal('');
  loading = signal(false);
  registrationComplete = signal(false);

  constructor(private auth: AuthService) {}

  register() {
    this.submitted.set(true);
    if (this.loading()) {
      return;
    }
    if (!this.name || !this.email || !this.password || !this.confirmPassword || this.passwordMismatch()) {
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.message.set('');
    this.registrationComplete.set(false);

    this.auth.register(this.name, this.email, this.password, this.role).subscribe({
      next: () => {
        this.message.set('Account created successfully.');
        this.password = '';
        this.confirmPassword = '';
        this.registrationComplete.set(true);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Registration failed');
        this.loading.set(false);
      }
    });
  }

  passwordMismatch() {
    return Boolean(this.confirmPassword && this.password && this.confirmPassword !== this.password);
  }

  togglePasswordVisibility() {
    this.showPassword.update(show => !show);
  }

  toggleConfirmPasswordVisibility() {
    this.showConfirmPassword.update(show => !show);
  }
}
