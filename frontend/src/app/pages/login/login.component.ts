import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { LucideEye, LucideEyeOff, LucideKeyRound, LucideLockKeyhole } from '@lucide/angular';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideEye, LucideEyeOff, LucideKeyRound, LucideLockKeyhole],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent {
  email = '';
  password = '';
  showPassword = signal(false);
  submitted = signal(false);
  error = signal('');
  message = signal('');
  loading = signal(false);

  constructor(
    private auth: AuthService,
    private router: Router
  ) {
    this.message.set(this.auth.consumeSessionMessage());
  }

  login() {
    this.submitted.set(true);
    if (!this.email || !this.password || this.loading()) {
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.message.set('');

    this.auth.login(this.email, this.password).subscribe({
      next: response => {
        this.auth.saveSession(response);
        this.router.navigate([this.auth.homeForRole(response.user.role)]);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Login failed');
        this.loading.set(false);
      }
    });
  }

  togglePasswordVisibility() {
    this.showPassword.update(show => !show);
  }
}
