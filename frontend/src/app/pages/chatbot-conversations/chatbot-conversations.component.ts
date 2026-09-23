import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-chatbot-conversations',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chatbot-conversations.component.html',
  styleUrls: ['./chatbot-conversations.component.css']
})
export class ChatbotConversationsComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;
  sessions = signal<any[]>([]);
  selectedSession = signal<any | null>(null);
  unansweredQuestions = signal<any[]>([]);
  loading = signal(false);
  detailsLoading = signal(false);
  unansweredLoading = signal(false);
  loadingMore = signal(false);
  followUpSaving = signal(false);
  hasMore = signal(false);
  error = signal('');
  message = signal('');
  search = '';
  dateFrom = '';
  dateTo = '';
  channel = '';
  responseType = '';
  followUpStatusDraft = 'new';
  managerNoteDraft = '';
  filtersOpen = false;
  private requestedSessionId = 0;
  private readonly pageSize = 25;
  private offset = 0;
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
    this.requestedSessionId = Number(this.route.snapshot.queryParamMap.get('sessionId') || 0);
    this.loadSessions();
    this.loadUnansweredQuestions();
    if (this.requestedSessionId) {
      this.openSessionById(this.requestedSessionId);
    }
  }

  loadSessions(append = false) {
    if (!append) {
      this.offset = 0;
      this.loading.set(true);
      this.selectedSession.set(null);
    } else {
      this.loadingMore.set(true);
    }
    this.error.set('');
    this.api.getChatbotConversations(this.chatbotId, {
      search: this.search,
      date_from: this.dateFrom,
      date_to: this.dateTo,
      channel: this.channel,
      response_type: this.responseType,
      limit: this.pageSize,
      offset: this.offset
    }).subscribe({
      next: sessions => {
        this.sessions.set(append ? [...this.sessions(), ...sessions] : sessions);
        this.hasMore.set((sessions || []).length === this.pageSize);
        this.offset += sessions.length;
        if (!append) {
          this.selectInitialConversation(sessions || []);
        }
        this.loading.set(false);
        this.loadingMore.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load conversations');
        this.loading.set(false);
        this.loadingMore.set(false);
      }
    });
  }

  loadMore() {
    if (this.loadingMore() || !this.hasMore()) return;
    this.loadSessions(true);
  }

  applyFilters() {
    this.filtersOpen = false;
    this.loadSessions();
  }

  loadUnansweredQuestions() {
    this.unansweredLoading.set(true);
    this.api.getChatbotUnansweredQuestions(this.chatbotId).subscribe({
      next: rows => {
        this.unansweredQuestions.set(rows || []);
        this.unansweredLoading.set(false);
      },
      error: () => {
        this.unansweredQuestions.set([]);
        this.unansweredLoading.set(false);
      }
    });
  }

  openSession(session: any) {
    this.detailsLoading.set(true);
    this.error.set('');
    this.message.set('');
    this.api.getChatbotConversation(this.chatbotId, session.id).subscribe({
      next: details => {
        this.setSelectedSession(details);
        this.detailsLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load conversation');
        this.detailsLoading.set(false);
      }
    });
  }

  clearFilters() {
    this.search = '';
    this.dateFrom = '';
    this.dateTo = '';
    this.channel = '';
    this.responseType = '';
    this.filtersOpen = false;
    this.loadSessions();
  }

  openSessionById(sessionId: number) {
    const match = this.sessions().find(session => session.id === sessionId);
    if (match) {
      this.openSession(match);
      return;
    }

    this.detailsLoading.set(true);
    this.error.set('');
    this.message.set('');
    this.api.getChatbotConversation(this.chatbotId, sessionId).subscribe({
      next: details => {
        this.setSelectedSession(details);
        this.detailsLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load conversation');
        this.detailsLoading.set(false);
      }
    });
  }

  closeDetails() {
    this.selectedSession.set(null);
  }

  channelLabel(value: string) {
    const labels: any = {
      public: 'Public chat',
      dashboard: 'Dashboard test',
      widget: 'Widget'
    };
    return labels[value] || value || 'Unknown';
  }

  responseLabel(value: string) {
    const labels: any = {
      ai_rag: 'AI/RAG',
      fallback: 'Fallback',
      flow: 'Flow',
      unknown: 'Unknown'
    };
    return labels[value] || value || 'Unknown';
  }

  followUpStatusLabel(value: string) {
    const labels: any = {
      new: 'New',
      followed_up: 'Followed up',
      scheduled: 'Scheduled',
      closed: 'Closed'
    };
    return labels[value] || 'New';
  }

  saveSelectedFollowUp() {
    const session = this.selectedSession();
    if (!session || this.followUpSaving()) return;

    const payload = {
      status: this.followUpStatusDraft || 'new',
      note: this.managerNoteDraft || ''
    };
    this.followUpSaving.set(true);
    this.error.set('');
    this.message.set('');
    this.api.updateConversationFollowUp(this.chatbotId, session.id, payload).subscribe({
      next: result => {
        const updatedSession = {
          ...session,
          follow_up_status: result.follow_up_status,
          manager_note: result.manager_note
        };
        this.setSelectedSession(updatedSession);
        this.sessions.update(sessions => sessions.map(item => item.id === session.id
          ? {
              ...item,
              follow_up_status: result.follow_up_status,
              manager_note: result.manager_note
            }
          : item
        ));
        this.message.set('Follow-up state saved.');
        this.followUpSaving.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save follow-up state');
        this.followUpSaving.set(false);
      }
    });
  }

  groupedSessions() {
    const groups: { label: string; sessions: any[] }[] = [];
    for (const session of this.sessions()) {
      const label = this.sessionGroupLabel(session);
      const group = groups.find(item => item.label === label);
      if (group) {
        group.sessions.push(session);
      } else {
        groups.push({ label, sessions: [session] });
      }
    }
    return groups;
  }

  sessionGroupLabel(session: any) {
    const value = session.updated_at || session.created_at;
    if (!value) return 'Older';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Older';
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfYesterday = startOfToday - 86400000;
    const time = date.getTime();
    if (time >= startOfToday) return 'Today';
    if (time >= startOfYesterday) return 'Yesterday';
    if (Date.now() - time < 7 * 86400000) return 'This week';
    return 'Older';
  }

  conversationTitle(session: any) {
    const message = this.cleanMessage(session.last_message);
    if (message) return this.truncate(message, 58);
    return `${this.channelLabel(session.channel)} session #${session.id}`;
  }

  conversationPreview(session: any) {
    const message = this.cleanMessage(session.last_message);
    return message ? this.truncate(message, 120) : 'No messages captured yet.';
  }

  activeFilterSummary() {
    const filters = [
      this.search ? 'Search' : '',
      this.dateFrom || this.dateTo ? 'Date range' : '',
      this.channel ? this.channelLabel(this.channel) : '',
      this.responseType ? this.responseLabel(this.responseType) : ''
    ].filter(Boolean);
    return filters.length ? filters.join(' · ') : 'All conversations';
  }

  hasActiveFilters() {
    return Boolean(this.search || this.dateFrom || this.dateTo || this.channel || this.responseType);
  }

  advancedFilterCount() {
    return [this.channel, this.responseType].filter(Boolean).length;
  }

  toggleFilters() {
    this.filtersOpen = !this.filtersOpen;
  }

  private selectInitialConversation(sessions: any[]) {
    if (this.requestedSessionId || !sessions.length || !this.isDesktopViewport()) return;
    this.openSession(sessions[0]);
  }

  private setSelectedSession(session: any) {
    this.selectedSession.set(session);
    this.followUpStatusDraft = session.follow_up_status || 'new';
    this.managerNoteDraft = session.manager_note || '';
  }

  private isDesktopViewport() {
    return this.isBrowser && window.matchMedia('(min-width: 941px)').matches;
  }

  private cleanMessage(value: unknown) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  private truncate(value: string, length: number) {
    return value.length > length ? `${value.slice(0, length).trim()}...` : value;
  }

  exportConversationsCsv() {
    const rows = [
      ['Session ID', 'Channel', 'Response Type', 'Messages', 'Created At', 'Last Activity', 'Last Message'],
      ...this.sessions().map(session => [
        session.id,
        this.channelLabel(session.channel),
        this.responseLabel(session.response_type),
        session.message_count,
        session.created_at,
        session.updated_at,
        session.last_message || ''
      ])
    ];
    const csv = rows.map(row => row.map(value => `"${String(value ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    this.downloadFile(`chatbot-${this.chatbotId}-conversations.csv`, csv, 'text/csv');
  }

  exportSelected(format: 'txt' | 'json') {
    const session = this.selectedSession();
    if (!session) return;

    if (format === 'json') {
      this.downloadFile(
        `conversation-${session.id}.json`,
        JSON.stringify(session, null, 2),
        'application/json'
      );
      return;
    }

    const transcript = [
      `Session #${session.id}`,
      `Channel: ${this.channelLabel(session.channel)}`,
      `Response type: ${this.responseLabel(session.response_type)}`,
      '',
      ...(session.messages || []).map((message: any) => (
        `[${message.created_at}] ${message.role.toUpperCase()}${message.response_mode ? ` (${this.responseLabel(message.response_mode)})` : ''}\n${message.content}`
      ))
    ].join('\n\n');
    this.downloadFile(`conversation-${session.id}.txt`, transcript, 'text/plain');
  }

  private downloadFile(filename: string, content: string, type: string) {
    if (!this.isBrowser) return;
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }
}
