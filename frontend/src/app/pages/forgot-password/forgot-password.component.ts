import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { LucideLockKeyhole } from '@lucide/angular';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-forgot-password',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideLockKeyhole],
  templateUrl: './forgot-password.component.html',
  styleUrls: ['../login/login.component.css']
})
export class ForgotPasswordComponent {
  email = '';
  submitted = signal(false);
  error = signal('');
  message = signal('');
  loading = signal(false);
  sent = signal(false);

  constructor(private auth: AuthService) {}

  submit() {
    this.submitted.set(true);
    if (!this.email || this.loading()) {
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.message.set('');
    this.sent.set(false);

    this.auth.forgotPassword(this.email).subscribe({
      next: response => {
        this.message.set(response.message || 'If an account exists for this email, a password reset link has been sent.');
        this.sent.set(true);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not request password reset');
        this.loading.set(false);
      }
    });
  }
}
