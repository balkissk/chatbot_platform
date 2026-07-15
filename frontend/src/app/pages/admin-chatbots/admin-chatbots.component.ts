import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../../services/api';

type ChatbotStats = {
  total: number;
  published: number;
  draft_only: number;
  disabled: number;
};

@Component({
  selector: 'app-admin-chatbots',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-chatbots.component.html',
  styleUrls: ['./admin-chatbots.component.css']
})
export class AdminChatbotsComponent implements OnInit {
  items = signal<any[]>([]);
  selected = signal<any | null>(null);
  stats = signal<ChatbotStats>({ total: 0, published: 0, draft_only: 0, disabled: 0 });
  total = signal(0);
  totalPages = signal(0);
  loading = signal(false);
  detailsLoading = signal(false);
  error = signal('');

  search = '';
  ownerId = '';
  projectId = '';
  publicationStatus = '';
  deploymentStatus = '';
  sortBy = 'created_at';
  sortOrder = 'desc';
  page = 1;
  pageSize = 10;

  private isBrowser: boolean;

  constructor(
    private api: ApiService,
    private router: Router,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.load();
  }

  load(reset = false) {
    if (!this.isBrowser) return;
    if (reset) this.page = 1;
    this.loading.set(true);
    this.error.set('');

    const params: any = {
      page: this.page,
      page_size: this.pageSize,
      sort_by: this.sortBy,
      sort_order: this.sortOrder
    };
    if (this.search.trim()) params.search = this.search.trim();
    if (this.ownerId) params.owner_id = Number(this.ownerId);
    if (this.projectId) params.project_id = Number(this.projectId);
    if (this.publicationStatus) params.publication_status = this.publicationStatus;
    if (this.deploymentStatus) params.deployment_status = this.deploymentStatus;

    this.api.getAdminChatbots(params).subscribe({
      next: payload => {
        this.items.set(payload.items || []);
        this.total.set(payload.total || 0);
        this.totalPages.set(payload.total_pages || 0);
        this.stats.set(payload.stats || { total: 0, published: 0, draft_only: 0, disabled: 0 });
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load admin chatbots');
        this.items.set([]);
        this.loading.set(false);
      }
    });
  }

  resetFilters() {
    this.search = '';
    this.ownerId = '';
    this.projectId = '';
    this.publicationStatus = '';
    this.deploymentStatus = '';
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';
    this.load(true);
  }

  nextPage() {
    if (this.page >= this.totalPages()) return;
    this.page += 1;
    this.load();
  }

  previousPage() {
    if (this.page <= 1) return;
    this.page -= 1;
    this.load();
  }

  pageLabel() {
    if (!this.total()) return '0 chatbots';
    const start = (this.page - 1) * this.pageSize + 1;
    const end = Math.min(start + this.items().length - 1, this.total());
    return `${start}-${end} of ${this.total()}`;
  }

  openDetails(bot: any) {
    this.detailsLoading.set(true);
    this.error.set('');
    this.selected.set(null);
    this.api.getAdminChatbot(bot.chatbot_id).subscribe({
      next: details => {
        this.selected.set(details);
        this.detailsLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load chatbot details');
        this.detailsLoading.set(false);
      }
    });
  }

  closeDetails() {
    this.selected.set(null);
  }

  viewConversations(bot: any) {
    this.router.navigate(['/admin/conversations'], {
      queryParams: { chatbotId: bot.chatbot_id }
    });
  }

  viewRuntimeLogs(bot: any) {
    this.router.navigate(['/admin/runtime-logs'], {
      queryParams: { chatbotId: bot.chatbot_id }
    });
  }

  publicationLabel(status: string) {
    const labels: Record<string, string> = {
      published: 'Published',
      draft_only: 'Draft only',
      disabled: 'Disabled'
    };
    return labels[status] || status || 'Unknown';
  }

  deploymentLabel(status: string) {
    return status === 'deployed' ? 'Deployed' : 'Not deployed';
  }

  channelLabel(channel: string) {
    const labels: Record<string, string> = {
      web: 'Public Chat',
      widget: 'Web Widget',
      api: 'REST API'
    };
    return labels[channel] || channel;
  }

  relativeDate(value: string | null | undefined) {
    if (!value) return 'Never';
    const date = new Date(value);
    const diff = Date.now() - date.getTime();
    const minute = 60 * 1000;
    const hour = 60 * minute;
    const day = 24 * hour;
    if (diff < minute) return 'Just now';
    if (diff < hour) return `${Math.floor(diff / minute)} min ago`;
    if (diff < day) return `${Math.floor(diff / hour)} h ago`;
    if (diff < 7 * day) return `${Math.floor(diff / day)} d ago`;
    return date.toLocaleDateString();
  }
}
