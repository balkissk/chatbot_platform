import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-flow-test',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './flow-test.component.html',
  styleUrls: ['./flow-test.component.css']
})
export class FlowTestComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;

  context = signal<any | null>(null);
  sessionId = signal<number | undefined>(undefined);
  messages = signal<{ role: 'user' | 'bot'; text: string; options?: string[]; mode?: string; retrievalMode?: string; sources?: any[] }[]>([]);
  input = '';
  loading = signal(false);
  error = signal('');
  errorInfo = signal<{ title: string; message: string; detail: string } | null>(null);

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
    this.loadContext();
  }

  loadContext() {
    this.loading.set(true);
    this.error.set('');
    this.errorInfo.set(null);
    this.api.getChatbotBuilder(this.chatbotId).subscribe({
      next: context => {
        this.context.set(context);
        this.loading.set(false);
        this.startTest();
      },
      error: err => {
        this.setFriendlyError(err, 'Flow validation error', 'Could not load flow test.');
        this.loading.set(false);
      }
    });
  }

  startTest() {
    const versionId = this.context()?.version?.id;
    if (!versionId) return;

    this.sessionId.set(undefined);
    this.messages.set([]);
    this.loading.set(true);
    this.error.set('');
    this.errorInfo.set(null);

    this.api.startChatSession({
      chatbot_id: this.chatbotId,
      version_id: versionId
    }).subscribe({
      next: session => {
        this.sessionId.set(session.session_id);
        this.loading.set(false);
        this.send('__start__');
      },
      error: err => {
        this.setFriendlyError(err, 'Database/session error', 'Could not start the test session.');
        this.loading.set(false);
      }
    });
  }

  send(option?: string) {
    const text = option || this.input.trim();
    if (!text) return;

    if (text !== '__start__') {
      this.messages.update(messages => [...messages, { role: 'user', text }]);
    }
    this.input = '';
    this.loading.set(true);
    this.error.set('');
    this.errorInfo.set(null);

    this.api.chat({
      chatbot_id: this.chatbotId,
      version_id: this.context()?.version?.id,
      session_id: this.sessionId(),
      message: text === '__start__' ? '' : text
    }).subscribe({
      next: result => {
        this.sessionId.set(result.session_id);
        this.messages.update(messages => [...messages, ...this.toBotMessages(result)]);
        this.loading.set(false);
      },
      error: err => {
        this.setFriendlyError(err, '', 'Flow test failed.');
        this.loading.set(false);
      }
    });
  }

  private toBotMessages(result: any) {
    const mode = result.mode_used || 'flow';
    const retrievalMode = result.retrieval_mode || '';
    const sources = result.sources || [];
    if (Array.isArray(result.messages) && result.messages.length > 0) {
      return result.messages.map((item: any) => ({
        role: 'bot' as const,
        text: item.text || '',
        options: item.options || [],
        mode,
        retrievalMode,
        sources
      }));
    }

    return [{
      role: 'bot' as const,
      text: result.response || '',
      options: result.options || [],
      mode,
      retrievalMode,
      sources
    }];
  }

  responseLabel(item: { mode?: string; retrievalMode?: string }) {
    const mode = item.mode || 'flow';
    if (mode.includes('rag')) return `AI/RAG${item.retrievalMode ? ' - ' + item.retrievalMode : ''}`;
    if (mode === 'fallback') return 'Fallback';
    if (item.retrievalMode === 'keyword') return 'Keyword retrieval';
    if (item.retrievalMode === 'semantic') return 'Semantic retrieval';
    return 'Flow message';
  }

  private setFriendlyError(err: any, preferredTitle: string, fallback: string) {
    const raw = err?.error?.detail || err?.message || fallback;
    const detail = typeof raw === 'object' ? JSON.stringify(raw) : String(raw);
    let title = preferredTitle || 'Flow validation error';
    let message = fallback;

    if (detail.includes('LLM service') || detail.includes('OpenAI') || detail.includes('Azure')) {
      title = 'AI service error';
      message = 'The AI service could not generate an answer right now.';
    } else if (detail.includes('knowledge') || detail.includes('embedding') || detail.includes('chunk')) {
      title = 'Knowledge base error';
      message = 'The knowledge base could not be used for this answer.';
    } else if (detail.includes('session') || detail.includes('database') || detail.includes('connection')) {
      title = 'Database/session error';
      message = 'The test session could not be saved or loaded.';
    } else if (!preferredTitle) {
      title = 'Flow validation error';
      message = 'The flow could not continue. Check the configured paths and blocks.';
    }

    this.error.set(message);
    this.errorInfo.set({ title, message, detail });
  }

  goBuilder() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'flow']);
  }
}
