import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import {
  LucideCheckCircle2,
  LucideClipboard,
  LucideCode2,
  LucideExternalLink,
  LucideGlobe2,
  LucideKeyRound,
  LucideRefreshCw,
  LucideRocket,
  LucideServer,
  LucideShieldCheck,
  LucideTriangleAlert,
  LucideX
} from '@lucide/angular';
import { apiBaseUrl, frontendBaseUrl } from '../../config/app-config';
import { ApiService } from '../../services/api';
import { ToastService } from '../../services/toast.service';

@Component({
  selector: 'app-chatbot-deployment',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    LucideCheckCircle2,
    LucideClipboard,
    LucideCode2,
    LucideExternalLink,
    LucideGlobe2,
    LucideKeyRound,
    LucideRefreshCw,
    LucideRocket,
    LucideServer,
    LucideShieldCheck,
    LucideTriangleAlert,
    LucideX
  ],
  templateUrl: './chatbot-deployment.component.html',
  styleUrls: ['./chatbot-deployment.component.css']
})
export class ChatbotDeploymentComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;
  project = signal<any | null>(null);
  assistant = signal<any | null>(null);
  channels = signal<any[]>([]);
  loading = signal(false);
  channelsLoading = signal(false);
  channelTesting = signal<string | undefined>(undefined);
  apiKeyId = signal<number | undefined>(undefined);
  pendingApiKeyReset = signal(false);
  error = signal('');
  success = signal('');
  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private toast: ToastService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
    if (!this.isBrowser) return;
    this.loadPage();
  }

  loadPage() {
    this.loading.set(true);
    this.error.set('');
    this.api.getProject(this.projectId).subscribe({
      next: project => this.project.set(project),
      error: () => this.project.set(null)
    });
    this.api.getChatbot(this.chatbotId).subscribe({
      next: assistant => {
        this.assistant.set(assistant);
        this.loading.set(false);
        this.loadChannels();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load assistant deployment');
        this.loading.set(false);
      }
    });
  }

  loadChannels() {
    this.channelsLoading.set(true);
    this.error.set('');
    this.api.getChatbotChannels(this.chatbotId).subscribe({
      next: channels => {
        this.channels.set(channels || []);
        this.channelsLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load deployment channels');
        this.channels.set([]);
        this.channelsLoading.set(false);
      }
    });
  }

  publicLink() {
    return `${frontendBaseUrl()}/public-chat/${this.chatbotId}`;
  }

  widgetCode() {
    const assistant = this.assistant();
    const baseUrl = apiBaseUrl();
    return `<script src="${baseUrl}/public/widget.js" data-api-base="${baseUrl}" data-chatbot-id="${this.chatbotId}" data-title="${assistant?.name || 'Support'}"></script>`;
  }

  apiEndpoint() {
    return `${apiBaseUrl()}/public/api/chat`;
  }

  apiCurl() {
    const assistant = this.assistant();
    return `curl -X POST "${this.apiEndpoint()}" \\
  -H "Content-Type: application/json" \\
  -H "x-chatbot-api-key: ${assistant?.public_api_key || 'YOUR_API_KEY'}" \\
  -d "{\\"chatbot_id\\":${this.chatbotId},\\"message\\":\\"Hello\\",\\"session_id\\":null}"`;
  }

  maskedApiKey() {
    const key = this.assistant()?.public_api_key || '';
    if (!key) return 'Not generated';
    return `${key.slice(0, 5)}${'*'.repeat(18)}${key.slice(-4)}`;
  }

  channel(type: string) {
    return this.channels().find(item => item.channel_type === type);
  }

  channelStatus(type: string) {
    return this.channel(type)?.status || (['web', 'widget', 'api'].includes(type) ? 'connected' : 'not_configured');
  }

  channelStatusLabel(type: string) {
    const value = this.channelStatus(type);
    const labels: Record<string, string> = {
      disconnected: 'Not configured',
      not_configured: 'Not configured',
      configured: 'Configured',
      verified: 'Verified',
      connected: 'Connected',
      deployed: 'Connected',
      error: 'Needs attention'
    };
    return labels[value] || value || 'Not configured';
  }

  channelStatusClass(type: string) {
    return `status-${this.channelStatus(type)}`;
  }

  statusSummary() {
    const statuses = ['web', 'widget', 'api'].map(type => this.channelStatus(type));
    if (statuses.includes('error')) return 'Needs attention';
    if (statuses.some(status => ['connected', 'verified', 'configured', 'deployed'].includes(status))) return 'Ready';
    return 'Draft';
  }

  copyText(text: string | undefined) {
    if (!text) {
      this.error.set('No value available to copy');
      return;
    }
    if (!this.isBrowser || !navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(() => {
      this.success.set('Copied to clipboard');
      this.toast.success('Copied to clipboard');
    });
  }

  testChannel(type: 'web' | 'widget' | 'api') {
    this.channelTesting.set(type);
    this.error.set('');
    this.success.set('');
    this.api.testChatbotChannel(this.chatbotId, type).subscribe({
      next: result => {
        this.channelTesting.set(undefined);
        const message = result.configured
          ? `${this.channelDisplayName(type)} channel is configured.`
          : `${this.channelDisplayName(type)} missing: ${(result.missing_fields || []).join(', ') || 'configuration'}`;
        this.success.set(message);
        this.toast.success(message);
        this.loadChannels();
      },
      error: err => {
        this.channelTesting.set(undefined);
        this.error.set(err.error?.detail || 'Could not test channel');
      }
    });
  }

  regenerateApiKey() {
    if (this.apiKeyId()) return;
    this.pendingApiKeyReset.set(true);
  }

  cancelRegenerateApiKey() {
    if (this.apiKeyId()) return;
    this.pendingApiKeyReset.set(false);
  }

  confirmRegenerateApiKey() {
    if (this.apiKeyId()) return;
    this.apiKeyId.set(this.chatbotId);
    this.error.set('');
    this.success.set('');
    this.api.regenerateChatbotApiKey(this.chatbotId).subscribe({
      next: response => {
        this.apiKeyId.set(undefined);
        this.pendingApiKeyReset.set(false);
        this.assistant.update(assistant => assistant ? { ...assistant, public_api_key: response.public_api_key } : assistant);
        this.success.set('API key regenerated');
        this.toast.success('API key regenerated');
      },
      error: err => {
        this.apiKeyId.set(undefined);
        this.error.set(err.error?.detail || 'Could not regenerate API key');
      }
    });
  }

  channelDisplayName(type: string) {
    const labels: Record<string, string> = {
      web: 'Public Chat',
      widget: 'Web Widget',
      api: 'REST API'
    };
    return labels[type] || type;
  }

  channelCurrentError(type: string) {
    const channel = this.channel(type);
    return channel?.last_error || channel?.last_error_log?.message || channel?.last_error?.message || '';
  }
}
