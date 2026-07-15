import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-admin-runtime-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-runtime-logs.component.html',
  styleUrls: ['./admin-runtime-logs.component.css']
})
export class AdminRuntimeLogsComponent implements OnInit {
  items = signal<any[]>([]);
  total = signal(0);
  loading = signal(false);
  error = signal('');

  chatbotId = '';
  status = '';
  channel = '';
  limit = 25;
  offset = 0;
  private isBrowser: boolean;

  constructor(
    private api: ApiService,
    private route: ActivatedRoute,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    const queryChatbotId = this.route.snapshot.queryParamMap.get('chatbotId');
    if (queryChatbotId) this.chatbotId = queryChatbotId;
    this.load(true);
  }

  load(reset = false) {
    if (!this.isBrowser) return;
    if (reset) this.offset = 0;
    this.loading.set(true);
    this.error.set('');

    const params: any = {
      limit: this.limit,
      offset: this.offset
    };
    if (this.chatbotId) params.chatbot_id = Number(this.chatbotId);
    if (this.status) params.status = this.status;
    if (this.channel) params.channel = this.channel;

    this.api.getAdminRuntimeLogs(params).subscribe({
      next: payload => {
        this.items.set(payload.items || []);
        this.total.set(payload.total || 0);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load runtime logs');
        this.items.set([]);
        this.loading.set(false);
      }
    });
  }

  resetFilters() {
    this.chatbotId = '';
    this.status = '';
    this.channel = '';
    this.load(true);
  }

  nextPage() {
    if (this.offset + this.limit >= this.total()) return;
    this.offset += this.limit;
    this.load();
  }

  previousPage() {
    if (this.offset === 0) return;
    this.offset = Math.max(0, this.offset - this.limit);
    this.load();
  }

  pageLabel() {
    if (!this.total()) return '0 logs';
    const start = this.offset + 1;
    const end = Math.min(this.offset + this.items().length, this.total());
    return `${start}-${end} of ${this.total()}`;
  }
}
