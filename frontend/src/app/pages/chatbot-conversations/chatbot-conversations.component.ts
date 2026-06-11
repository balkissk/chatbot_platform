import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
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
  hasMore = signal(false);
  error = signal('');
  search = '';
  dateFrom = '';
  dateTo = '';
  channel = '';
  feedback = '';
  responseType = '';
  private readonly pageSize = 25;
  private offset = 0;
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
    this.loadSessions();
    this.loadUnansweredQuestions();
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
      feedback: this.feedback,
      response_type: this.responseType,
      limit: this.pageSize,
      offset: this.offset
    }).subscribe({
      next: sessions => {
        this.sessions.set(append ? [...this.sessions(), ...sessions] : sessions);
        this.hasMore.set((sessions || []).length === this.pageSize);
        this.offset += sessions.length;
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
    this.api.getChatbotConversation(this.chatbotId, session.id).subscribe({
      next: details => {
        this.selectedSession.set(details);
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
    this.feedback = '';
    this.responseType = '';
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
    this.api.getChatbotConversation(this.chatbotId, sessionId).subscribe({
      next: details => {
        this.selectedSession.set(details);
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

  feedbackLabel(value: string) {
    const labels: any = {
      positive: 'Helpful',
      negative: 'Not helpful',
      no_feedback: 'No feedback'
    };
    return labels[value] || 'No feedback';
  }

  exportConversationsCsv() {
    const rows = [
      ['Session ID', 'Channel', 'Feedback', 'Response Type', 'Messages', 'Created At', 'Last Activity', 'Last Message'],
      ...this.sessions().map(session => [
        session.id,
        this.channelLabel(session.channel),
        this.feedbackLabel(session.feedback_status),
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
      `Feedback: ${this.feedbackLabel(session.feedback_status)}`,
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

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }
}
