import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './admin-dashboard.component.html',
  styleUrls: ['./admin-dashboard.component.css']
})
export class AdminDashboardComponent implements OnInit {
  overview = signal<any | null>(null);
  loading = signal(false);
  error = signal('');
  private isBrowser: boolean;

  constructor(
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.api.getAdminAnalyticsOverview().subscribe({
      next: overview => {
        this.overview.set(overview);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load dashboard');
        this.loading.set(false);
      }
    });
  }
}
