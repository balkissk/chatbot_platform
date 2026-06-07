import { CommonModule } from '@angular/common';
import { Component, OnDestroy, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './register.component.html',
  styleUrls: ['../login/login.component.css']
})
export class RegisterComponent implements OnDestroy {
  name = '';
  email = '';
  password = '';
  role = 'manager';
  error = signal('');
  message = signal('');
  loading = signal(false);
  registrationComplete = signal(false);
  private redirectTimer?: ReturnType<typeof setTimeout>;

  constructor(
    private auth: AuthService,
    private router: Router
  ) {}

  ngOnDestroy() {
    if (this.redirectTimer) {
      clearTimeout(this.redirectTimer);
    }
  }

  register() {
    if (this.loading() || this.registrationComplete()) {
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.message.set('');
    this.registrationComplete.set(false);

    this.auth.register(this.name, this.email, this.password, this.role).subscribe({
      next: () => {
        this.message.set('Account created successfully. Redirecting to login...');
        this.password = '';
        this.registrationComplete.set(true);
        this.loading.set(false);
        this.redirectTimer = setTimeout(() => {
          this.router.navigate(['/login']);
        }, 2000);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Registration failed');
        this.loading.set(false);
      }
    });
  }
}
