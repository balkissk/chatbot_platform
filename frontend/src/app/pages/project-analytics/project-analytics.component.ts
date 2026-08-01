import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-project-analytics',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './project-analytics.component.html',
  styleUrls: ['./project-analytics.component.css']
})
export class ProjectAnalyticsComponent implements OnInit {
  projectId!: number;
  analytics = signal<any | null>(null);
  loading = signal(false);
  error = signal('');
  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    if (!this.isBrowser) return;
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.api.getProjectAnalytics(this.projectId).subscribe({
      next: analytics => {
        this.analytics.set(analytics);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load project analytics');
        this.loading.set(false);
      }
    });
  }

  kpis() {
    const data = this.analytics()?.kpis || {};
    return [
      { label: 'Conversations', value: data.conversations_count, helper: 'Recorded project sessions' },
      { label: 'Messages', value: data.messages_count, helper: 'User and assistant messages' },
      { label: 'Runtime Requests', value: data.runtime_request_count, helper: `${data.runtime_failure_count || 0} failed request(s)` },
      { label: 'Success Rate', value: data.runtime_success_rate === null || data.runtime_success_rate === undefined ? 'No data' : `${data.runtime_success_rate}%`, helper: 'Persisted runtime executions' },
      { label: 'Avg Latency', value: data.average_response_latency_ms === null || data.average_response_latency_ms === undefined ? 'No data' : `${data.average_response_latency_ms}ms`, helper: 'Average response time' },
      { label: 'Fallback Rate', value: data.fallback_rate === null || data.fallback_rate === undefined ? 'No data' : `${data.fallback_rate}%`, helper: `${data.fallback_count || 0} fallback response(s)` }
    ];
  }

  maxChannelCount() {
    return Math.max(...(this.analytics()?.usage_by_channel || []).map((item: any) => Number(item.count) || 0), 1);
  }

  barWidth(count: number) {
    return `${Math.max((Number(count) / this.maxChannelCount()) * 100, count ? 6 : 0)}%`;
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId]);
  }
}
