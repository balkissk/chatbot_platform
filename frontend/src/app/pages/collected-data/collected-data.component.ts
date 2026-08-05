import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-collected-data',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './collected-data.component.html',
  styleUrls: ['./collected-data.component.css']
})
export class CollectedDataComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;
  items = signal<any[]>([]);
  records = computed(() => this.buildRecords(this.items()));
  summary = signal<any>({});
  total = signal(0);
  loading = signal(false);
  savingSession = signal<number | null>(null);
  error = signal('');
  message = signal('');
  search = '';
  fieldType = '';
  statusDrafts: Record<number, string> = {};
  noteDrafts: Record<number, string> = {};
  private readonly pageSize = 100;
  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
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
    this.message.set('');
    this.api.getChatbotCollectedData(this.chatbotId, {
      search: this.search,
      field_type: this.fieldType,
      limit: this.pageSize,
      offset: 0
    }).subscribe({
      next: result => {
        const items = result.items || [];
        this.items.set(items);
        this.summary.set(result.summary || {});
        this.total.set(result.total || 0);
        for (const group of this.buildRecords(items)) {
          this.statusDrafts[group.sessionId] = group.status;
          this.noteDrafts[group.sessionId] = group.note;
        }
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load collected data');
        this.loading.set(false);
      }
    });
  }

  clearFilters() {
    this.search = '';
    this.fieldType = '';
    this.load();
  }

  typeLabel(value: string) {
    const labels: Record<string, string> = {
      name: 'Name',
      email: 'Email',
      phone: 'Phone',
      meeting: 'Meeting',
      selection: 'Selection',
      custom: 'Custom'
    };
    return labels[value] || value || 'Custom';
  }

  typeClass(value: string) {
    return `type-${value || 'custom'}`;
  }

  statusLabel(value: string) {
    const labels: Record<string, string> = {
      new: 'New',
      followed_up: 'Followed up',
      scheduled: 'Scheduled',
      closed: 'Closed'
    };
    return labels[value] || 'New';
  }

  private buildRecords(items: any[]) {
    const groups = new Map<number, any>();
    for (const item of items) {
      const group = groups.get(item.session_id) || {
        sessionId: item.session_id,
        channel: item.channel,
        messageCount: item.message_count,
        lastUserMessage: item.last_user_message,
        updatedAt: item.updated_at,
        status: item.follow_up_status || 'new',
        note: item.manager_note || '',
        fields: [],
        otherFields: [],
        name: '',
        email: '',
        phone: '',
        meeting: '',
        title: 'Collected record'
      };
      group.fields.push(item);
      if (item.type === 'name' && !group.name) group.name = item.value || '';
      if (item.type === 'email' && !group.email) group.email = item.value || '';
      if (item.type === 'phone' && !group.phone) group.phone = item.value || '';
      if (item.type === 'meeting' && !group.meeting) group.meeting = item.value || '';
      if (!['name', 'email', 'phone', 'meeting'].includes(item.type)) {
        group.otherFields.push(item);
      }
      group.title = group.name || group.email || group.phone || 'Collected record';
      if (new Date(item.updated_at || 0).getTime() > new Date(group.updatedAt || 0).getTime()) {
        group.updatedAt = item.updated_at;
      }
      groups.set(item.session_id, group);
    }
    return Array.from(groups.values()).sort((a, b) => new Date(b.updatedAt || 0).getTime() - new Date(a.updatedAt || 0).getTime());
  }

  trackRecord(_index: number, record: any) {
    return record.sessionId;
  }

  trackField(_index: number, item: any) {
    return `${item.session_id}-${item.field}-${item.value}`;
  }

  saveFollowUp(record: any) {
    this.savingSession.set(record.sessionId);
    this.error.set('');
    this.message.set('');
    this.api.updateConversationFollowUp(this.chatbotId, record.sessionId, {
      status: this.statusDrafts[record.sessionId] || 'new',
      note: this.noteDrafts[record.sessionId] || ''
    }).subscribe({
      next: result => {
        this.items.update(items => items.map(item => item.session_id === record.sessionId
          ? {
              ...item,
              follow_up_status: result.follow_up_status,
              manager_note: result.manager_note
            }
          : item
        ));
        this.message.set('Follow-up state saved.');
        this.savingSession.set(null);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save follow-up state');
        this.savingSession.set(null);
      }
    });
  }

  channelLabel(value: string) {
    const labels: Record<string, string> = {
      public: 'Public chat',
      dashboard: 'Dashboard test',
      widget: 'Widget'
    };
    return labels[value] || value || 'Unknown';
  }

  copyValue(value: string) {
    if (!this.isBrowser || !navigator.clipboard) return;
    navigator.clipboard.writeText(value || '');
  }

  exportCsv() {
    if (!this.isBrowser || !this.items().length) return;
    const rows = [
      ['Session', 'Status', 'Type', 'Label', 'Field', 'Value', 'Channel', 'Updated at', 'Manager note'],
      ...this.items().map(item => [
        item.session_id,
        this.statusLabel(item.follow_up_status),
        this.typeLabel(item.type),
        item.label,
        item.field,
        item.value,
        this.channelLabel(item.channel),
        item.updated_at || '',
        item.manager_note || ''
      ])
    ];
    const csv = rows.map(row => row.map(value => `"${String(value ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `assistant-${this.chatbotId}-collected-data.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
}
