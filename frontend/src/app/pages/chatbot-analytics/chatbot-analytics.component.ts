import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-chatbot-analytics',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './chatbot-analytics.component.html',
  styleUrls: ['./chatbot-analytics.component.css']
})
export class ChatbotAnalyticsComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;
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
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
    if (!this.isBrowser) return;
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.api.getChatbotAnalytics(this.chatbotId).subscribe({
      next: analytics => {
        this.analytics.set(analytics);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load analytics');
        this.loading.set(false);
      }
    });
  }

  maxValue(items: any[], key = 'count') {
    return Math.max(...(items || []).map(item => Number(item[key]) || 0), 1);
  }

  barHeight(value: number, items: any[]) {
    return `${Math.max((Number(value) / this.maxValue(items)) * 100, value ? 8 : 2)}%`;
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }
}
