import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-admin-conversations',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-conversations.component.html',
  styleUrls: ['./admin-conversations.component.css']
})
export class AdminConversationsComponent implements OnInit {
  sessions = signal<any[]>([]);
  selectedSession = signal<any | null>(null);
  loading = signal(false);
  detailsLoading = signal(false);
  error = signal('');
  chatbotFilter = '';
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
    this.loadSessions();
    const sessionId = Number(this.route.snapshot.queryParamMap.get('sessionId'));
    if (sessionId) this.openSession(sessionId);
  }

  loadSessions() {
    this.loading.set(true);
    this.error.set('');
    const chatbotId = Number(this.chatbotFilter);
    this.api.getAdminSessions(chatbotId || undefined).subscribe({
      next: sessions => {
        this.sessions.set(sessions);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load conversations');
        this.loading.set(false);
      }
    });
  }

  openSession(sessionId: number) {
    this.detailsLoading.set(true);
    this.error.set('');
    this.api.getAdminSession(sessionId).subscribe({
      next: session => {
        this.selectedSession.set(session);
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
}
