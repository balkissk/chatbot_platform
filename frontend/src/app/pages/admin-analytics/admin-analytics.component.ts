import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-admin-analytics',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-analytics.component.html',
  styleUrls: ['./admin-analytics.component.css']
})
export class AdminAnalyticsComponent implements OnInit {
  payload = signal<any | null>(null);
  loading = signal(false);
  error = signal('');
  range = '30d';
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
    if (!this.isBrowser) return;
    this.loading.set(true);
    this.error.set('');

    this.api.getAdminPlatformAnalytics(this.range).subscribe({
      next: payload => {
        this.payload.set(payload);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load analytics');
        this.payload.set(null);
        this.loading.set(false);
      }
    });
  }

  formatNumber(value: number | null | undefined) {
    if (value === null || value === undefined) return 'Unavailable';
    return new Intl.NumberFormat().format(value);
  }

  formatMs(value: number | null | undefined) {
    if (value === null || value === undefined) return 'Unavailable';
    return `${value} ms`;
  }

  formatPercent(value: number | null | undefined) {
    if (value === null || value === undefined) return 'Unavailable';
    return `${value}%`;
  }

  publicationLabel(status: string) {
    const labels: Record<string, string> = {
      published: 'Published',
      draft_only: 'Draft only',
      disabled: 'Disabled'
    };
    return labels[status] || status || 'Unknown';
  }

  chartPoints(values: number[] = []) {
    if (!values.length) return '';
    const max = Math.max(...values, 1);
    const width = 680;
    const height = 180;
    const step = values.length > 1 ? width / (values.length - 1) : width;
    return values
      .map((value, index) => {
        const x = index * step;
        const y = height - (value / max) * (height - 12) - 6;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  }

  maxValue(values: number[] = []) {
    return Math.max(...values, 0);
  }

  barWidth(value: number, values: number[]) {
    const max = Math.max(...values, 1);
    return `${Math.max((value / max) * 100, value > 0 ? 4 : 0)}%`;
  }

  hasAny(values: number[] = []) {
    return values.some(value => value > 0);
  }

  runtimeTotalSeries(payload: any) {
    return payload?.runtime_requests_over_time?.total_requests || [];
  }
}
