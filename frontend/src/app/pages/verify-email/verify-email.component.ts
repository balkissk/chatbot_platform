import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-verify-email',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './verify-email.component.html',
  styleUrls: ['../login/login.component.css']
})
export class VerifyEmailComponent implements OnInit {
  loading = signal(true);
  message = signal('');
  error = signal('');

  constructor(
    private route: ActivatedRoute,
    private auth: AuthService
  ) {}

  ngOnInit() {
    const token = this.route.snapshot.queryParamMap.get('token');
    if (!token) {
      this.error.set('Verification token is missing');
      this.loading.set(false);
      return;
    }

    this.auth.verifyEmail(token).subscribe({
      next: response => {
        this.message.set(response.message);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Email verification failed');
        this.loading.set(false);
      }
    });
  }
}
