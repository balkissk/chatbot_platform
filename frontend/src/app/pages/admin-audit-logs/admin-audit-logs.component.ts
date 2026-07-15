import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-admin-audit-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-audit-logs.component.html',
  styleUrls: ['./admin-audit-logs.component.css']
})
export class AdminAuditLogsComponent implements OnInit {
  items = signal<any[]>([]);
  total = signal(0);
  loading = signal(false);
  error = signal('');

  search = '';
  action = '';
  resourceType = '';
  dateFrom = '';
  dateTo = '';
  limit = 25;
  offset = 0;
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

  load(reset = false) {
    if (!this.isBrowser) return;
    if (reset) this.offset = 0;
    this.loading.set(true);
    this.error.set('');

    const params: any = {
      limit: this.limit,
      offset: this.offset
    };
    if (this.search.trim()) params.search = this.search.trim();
    if (this.action) params.action = this.action;
    if (this.resourceType) params.resource_type = this.resourceType;
    if (this.dateFrom) params.date_from = new Date(this.dateFrom).toISOString();
    if (this.dateTo) params.date_to = new Date(this.dateTo).toISOString();

    this.api.getAdminAuditLogs(params).subscribe({
      next: payload => {
        this.items.set(payload.items || []);
        this.total.set(payload.total || 0);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load audit logs');
        this.loading.set(false);
      }
    });
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

  resetFilters() {
    this.search = '';
    this.action = '';
    this.resourceType = '';
    this.dateFrom = '';
    this.dateTo = '';
    this.load(true);
  }

  pageLabel() {
    if (!this.total()) return '0 records';
    const start = this.offset + 1;
    const end = Math.min(this.offset + this.items().length, this.total());
    return `${start}-${end} of ${this.total()}`;
  }
}
