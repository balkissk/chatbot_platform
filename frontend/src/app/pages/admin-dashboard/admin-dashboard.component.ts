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

  valueOrUnavailable(value: unknown) {
    return value === null || value === undefined || value === '' ? 'Unavailable' : value;
  }

  metricPercent(value: number | null | undefined) {
    return value === null || value === undefined ? 'Unavailable' : `${value}%`;
  }

  msValue(value: number | null | undefined) {
    return value === null || value === undefined ? 'Unavailable' : `${value} ms`;
  }

  channelTotal(channels: any) {
    return Object.values(channels || {}).reduce((total: number, value: any) => total + Number(value || 0), 0);
  }

  channelGradient(channels: any) {
    const total = this.channelTotal(channels);
    if (!total) return '';

    const publicPct = (Number(channels.public_chat || 0) / total) * 100;
    const widgetPct = publicPct + (Number(channels.widget || 0) / total) * 100;
    const apiPct = widgetPct + (Number(channels.api || 0) / total) * 100;

    return `conic-gradient(#fff 0 ${publicPct}%, rgba(255,255,255,.72) ${publicPct}% ${widgetPct}%, rgba(255,255,255,.48) ${widgetPct}% ${apiPct}%, rgba(255,255,255,.18) ${apiPct}% 100%)`;
  }

  maxUsageValue(usage: any) {
    const values = [
      ...(usage?.conversations || []),
      ...((usage?.runtime_requests || []) as number[])
    ];
    return Math.max(...values, 1);
  }

  usageHeight(value: number, usage: any) {
    return Math.max(8, Math.round((Number(value || 0) / this.maxUsageValue(usage)) * 100));
  }

}
