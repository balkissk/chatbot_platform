import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './register.component.html',
  styleUrls: ['../login/login.component.css']
})
export class RegisterComponent {
  name = '';
  email = '';
  password = '';
  role = 'manager';
  error = signal('');
  message = signal('');
  loading = signal(false);
  registrationComplete = signal(false);

  constructor(private auth: AuthService) {}

  register() {
    if (this.loading()) {
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
        this.registrationComplete.set(true);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Registration failed');
        this.loading.set(false);
      }
    });
  }
}
