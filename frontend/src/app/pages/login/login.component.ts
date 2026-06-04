import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent {
  email = '';
  password = '';
  error = signal('');
  message = signal('');
  loading = signal(false);

  constructor(
    private auth: AuthService,
    private router: Router
  ) {}

  login() {
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
}
