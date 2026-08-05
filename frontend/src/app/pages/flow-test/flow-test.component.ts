import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, ElementRef, Inject, OnInit, PLATFORM_ID, ViewChild, signal } from '@angular/core';
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
  @ViewChild('messagesContainer') private messagesContainer?: ElementRef<HTMLElement>;
  @ViewChild('messageInput') private messageInput?: ElementRef<HTMLInputElement>;

  projectId!: number;
  chatbotId!: number;

  context = signal<any | null>(null);
  sessionId = signal<number | undefined>(undefined);
  messages = signal<{ role: 'user' | 'bot'; text: string; options?: string[]; mode?: string; retrievalMode?: string; sources?: any[]; failed?: boolean; streaming?: boolean; pending?: boolean }[]>([]);
  input = '';
  loading = signal(false);
  error = signal('');
  errorInfo = signal<{ title: string; message: string; detail: string } | null>(null);
  debugState = signal<any | null>(null);

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
    this.debugState.set(null);
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

  async send(option?: string) {
    if (this.loading()) return;

    const text = option || this.input.trim();
    if (!text) return;

    const requestStartedAt = this.nowMs();
    const clientSendEpochMs = Date.now();
    const shouldShowUserMessage = text !== '__start__';
    this.messages.update(messages => [
      ...messages,
      ...(shouldShowUserMessage ? [{ role: 'user' as const, text }] : []),
      { role: 'bot' as const, text: '', streaming: true, pending: true }
    ]);
    this.queueChatUiUpdate();
    this.input = '';
    this.loading.set(true);
    this.error.set('');
    this.errorInfo.set(null);

    let requestPreparedMs = 0;
    let firstFrontendChunkReceivedMs: number | null = null;
    let firstTokenRenderedMs: number | null = null;
    const streamingIndex = this.messages().length - 1;

    try {
      const payload = {
        chatbot_id: this.chatbotId,
        version_id: this.context()?.version?.id,
        session_id: this.sessionId(),
        message: text === '__start__' ? '' : text,
        client_send_at_ms: clientSendEpochMs
      };
      requestPreparedMs = this.nowMs() - requestStartedAt;
      await this.api.chatStream(payload, event => {
        if (event.type === 'start') {
          this.sessionId.set(event.session_id);
          this.updateDebugState(event);
          return;
        }

        if (event.type === 'token') {
          if (firstFrontendChunkReceivedMs === null) {
            firstFrontendChunkReceivedMs = (event.__frontend_chunk_received_at_ms || this.nowMs()) - requestStartedAt;
          }
          this.messages.update(messages => messages.map((item, index) => (
            index === streamingIndex
              ? { ...item, text: `${item.text}${event.text || ''}`, pending: false }
              : item
          )));
          if (firstTokenRenderedMs === null) {
            requestAnimationFrame(() => {
              if (firstTokenRenderedMs === null) {
                firstTokenRenderedMs = this.nowMs() - requestStartedAt;
              }
            });
          }
          this.queueChatUiUpdate();
          return;
        }

        if (event.type === 'final') {
          this.sessionId.set(event.session_id);
          this.updateDebugState(event);
          const botMessages = this.toBotMessages(event);
          this.messages.update(messages => {
            return [
              ...messages.slice(0, streamingIndex),
              ...botMessages,
              ...messages.slice(streamingIndex + 1)
            ];
          });
          if (firstTokenRenderedMs === null && firstFrontendChunkReceivedMs !== null) {
            firstTokenRenderedMs = this.nowMs() - requestStartedAt;
          }
          this.logLatency('final', {
            frontend_request_preparation_ms: Math.round(requestPreparedMs),
            frontend_first_chunk_received_ms: firstFrontendChunkReceivedMs === null ? null : Math.round(firstFrontendChunkReceivedMs),
            frontend_first_token_render_ms: firstTokenRenderedMs === null ? null : Math.round(firstTokenRenderedMs),
            frontend_total_ms: Math.round(this.nowMs() - requestStartedAt),
            backend: event.latency || {}
          });
          this.loading.set(false);
          this.queueChatUiUpdate();
          return;
        }

        if (event.type === 'error') {
          throw new Error(event.detail || 'Flow test failed.');
        }
      });
      if (this.loading()) {
        this.loading.set(false);
      }
    } catch (err: any) {
      this.setFriendlyError(err, '', 'Flow test failed.');
      const issue = this.errorInfo();
      if (text !== '__start__' && issue) {
        this.messages.update(messages => {
          const next = messages.filter((_, index) => index !== streamingIndex);
          return [
            ...next,
            {
              role: 'bot',
              text: issue.message,
              failed: true
            }
          ];
        });
      }
      this.logLatency('error', {
        frontend_request_preparation_ms: Math.round(requestPreparedMs),
        frontend_first_chunk_received_ms: firstFrontendChunkReceivedMs === null ? null : Math.round(firstFrontendChunkReceivedMs),
        frontend_first_token_render_ms: firstTokenRenderedMs === null ? null : Math.round(firstTokenRenderedMs),
        frontend_total_ms: Math.round(this.nowMs() - requestStartedAt)
      });
      this.loading.set(false);
      this.queueChatUiUpdate();
    }
  }

  private toBotMessages(result: any) {
    const mode = result.mode_used || 'flow';
    const retrievalMode = result.retrieval_mode || '';
    const sources = this.showSourceReferences() ? result.sources || [] : [];
    if (Array.isArray(result.messages) && result.messages.length > 0) {
      return result.messages
        .map((item: any) => ({
          role: 'bot' as const,
          text: item.text || '',
          options: this.chatOptions(item.options || []),
          mode,
          retrievalMode,
          sources
        }))
        .filter((item: any) => item.text.trim() || item.options.length);
    }

    const message = {
      role: 'bot' as const,
      text: result.response || '',
      options: this.chatOptions(result.options || []),
      mode,
      retrievalMode,
      sources
    };

    return message.text.trim() || message.options.length ? [message] : [];
  }

  chatOptions(options?: string[]) {
    return (options || []).filter(option => {
      const value = String(option || '').trim();
      return value && value.toLowerCase() !== 'next';
    });
  }

  showSourceReferences() {
    return this.context()?.chatbot?.rag_settings?.show_sources !== false;
  }

  currentBlockLabel() {
    const key = this.debugState()?.current_node_key;
    if (!key) return 'Completed';
    const node = this.context()?.flow?.nodes?.find((item: any) => item.node_key === key || item.key === key);
    return node?.label || key;
  }

  currentBlockType() {
    const key = this.debugState()?.current_node_key;
    if (!key) return 'end';
    const node = this.context()?.flow?.nodes?.find((item: any) => item.node_key === key || item.key === key);
    return node?.node_type || node?.type || 'unknown';
  }

  modeLabel() {
    return String(this.debugState()?.mode_used || 'flow').replace(/_/g, ' ');
  }

  sourceCount() {
    return this.debugState()?.sources?.length || 0;
  }

  visibleVariables() {
    const variables = this.debugState()?.variables || {};
    return Object.entries(variables)
      .filter(([key, value]) => !key.startsWith('__') && value !== null && value !== undefined && String(value).trim())
      .map(([key, value]) => ({ key, value: this.formatDebugValue(value) }));
  }

  hasStreamingResponse() {
    return this.messages().some(item => item.streaming);
  }

  senderLabel(item: { role: 'user' | 'bot' }) {
    return item.role === 'user' ? 'User' : 'Assistant';
  }

  private queueChatUiUpdate() {
    if (!this.isBrowser) return;

    window.setTimeout(() => {
      const container = this.messagesContainer?.nativeElement;
      if (container) {
        container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
      }
      this.messageInput?.nativeElement?.focus();
    });
  }

  private nowMs() {
    return this.isBrowser && typeof performance !== 'undefined'
      ? performance.now()
      : Date.now();
  }

  private logLatency(status: string, metrics: any) {
    if (!this.isBrowser) return;
    console.info('ChatBot Factory Test Flow latency', { status, ...metrics });
  }

  private updateDebugState(event: any) {
    this.debugState.set({
      session_id: event.session_id || this.sessionId(),
      current_node_key: event.current_node_key ?? this.debugState()?.current_node_key,
      variables: event.variables || this.debugState()?.variables || {},
      mode_used: event.mode_used || this.debugState()?.mode_used || 'flow',
      sources: event.sources || []
    });
  }

  private formatDebugValue(value: unknown) {
    if (typeof value === 'string') return value;
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  private setFriendlyError(err: any, preferredTitle: string, fallback: string) {
    const raw = err?.error?.detail || err?.message || fallback;
    const detail = typeof raw === 'object' ? JSON.stringify(raw) : String(raw);
    let title = preferredTitle || 'Flow validation error';
    let message = fallback;

    if (detail.includes('LLM service') || detail.includes('OpenAI') || detail.includes('Azure')) {
      title = 'AI service error';
      message = 'The AI service could not generate an answer right now.';
    } else if (detail === 'Not Found' || detail.includes('/chat/stream')) {
      title = 'Backend route missing';
      message = 'The test chat endpoint is not available from the running backend.';
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
