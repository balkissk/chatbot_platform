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
  messages = signal<{ role: 'user' | 'bot'; text: string; options?: string[] }[]>([]);
  input = '';
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
    this.loadContext();
  }

  loadContext() {
    this.loading.set(true);
    this.error.set('');
    this.api.getChatbotBuilder(this.chatbotId).subscribe({
      next: context => {
        this.context.set(context);
        this.loading.set(false);
        this.startTest();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load flow test');
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
        this.error.set(err.error?.detail || 'Could not start test session');
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
        this.error.set(err.error?.detail || 'Flow test failed');
        this.loading.set(false);
      }
    });
  }

  private toBotMessages(result: any) {
    if (Array.isArray(result.messages) && result.messages.length > 0) {
      return result.messages.map((item: any) => ({
        role: 'bot' as const,
        text: item.text || '',
        options: item.options || []
      }));
    }

    return [{
      role: 'bot' as const,
      text: result.response || '',
      options: result.options || []
    }];
  }

  goBuilder() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots', this.chatbotId, 'flow']);
  }
}
