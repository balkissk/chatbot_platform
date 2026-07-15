import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';
import { apiBaseUrl, frontendBaseUrl } from '../../config/app-config';
import { AssistantCreationWizardComponent } from './assistant-creation-wizard.component';

@Component({
  selector: 'app-chatbots',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, AssistantCreationWizardComponent],
  templateUrl: './chatbots.component.html',
  styleUrls: ['./chatbots.component.css']
})
export class ChatbotsComponent implements OnInit {
  projectId!: number;
  project = signal<any | null>(null);
  chatbots = signal<any[]>([]);
  wizardOpen = signal(false);
  loading = signal(false);
  refreshing = signal(false);
  creating = signal(false);
  savingId = signal<number | undefined>(undefined);
  deletingId = signal<number | undefined>(undefined);
  statusId = signal<number | undefined>(undefined);
  apiKeyId = signal<number | undefined>(undefined);
  editingId = signal<number | undefined>(undefined);
  selectedDetails = signal<any | null>(null);
  channels = signal<any[]>([]);
  channelsLoading = signal(false);
  detailsMode = signal<'overview' | 'deploy' | 'settings'>('overview');
  detailsLoading = signal(false);
  error = signal('');
  success = signal('');
  editForm = {
    name: '',
    description: '',
    language: 'fr',
    type: 'builder',
    purpose: 'custom',
    mode: 'builder',
    channel: 'web_widget',
    template_key: null as string | null
  };
  channelSaving = signal<string | undefined>(undefined);
  channelTesting = signal<string | undefined>(undefined);
  private isBrowser: boolean;
  private pendingDeployChatbotId: number | undefined;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private router: Router,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    if (!this.isBrowser) return;
    const query = this.route.snapshot.queryParamMap;
    const returnedChatbotId = Number(query.get('chatbot_id'));
    if (query.get('mode') === 'deploy' && returnedChatbotId) {
      this.pendingDeployChatbotId = returnedChatbotId;
    }
    this.loadProject();
    const cachedChatbots = this.api.getCachedChatbotsByProject(this.projectId);
    if (cachedChatbots) {
      this.chatbots.set(cachedChatbots);
      this.loadChatbots(true, true);
    } else {
      this.loadChatbots();
    }
  }

  loadProject(force = false) {
    if (!this.isBrowser) return;

    this.api.getProject(this.projectId, force).subscribe({
      next: project => {
        this.project.set(project);
      },
      error: () => {
        this.project.set(null);
      }
    });
  }

  loadChatbots(force = false, background = false) {
    if (!this.isBrowser) return;

    const hasVisibleData = this.chatbots().length > 0;
    if (background || hasVisibleData) {
      this.refreshing.set(true);
    } else {
      this.loading.set(true);
    }
    this.error.set('');
    if (!background) {
      this.success.set('');
    }

    this.api.getChatbotsByProject(this.projectId, force).subscribe({
      next: chatbots => {
        this.chatbots.set(chatbots);
        this.loading.set(false);
        this.refreshing.set(false);
        this.openPendingDeployPanel(chatbots);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load chatbots');
        this.loading.set(false);
        this.refreshing.set(false);
      }
    });
  }

  openPendingDeployPanel(chatbots: any[]) {
    if (!this.pendingDeployChatbotId) return;
    const bot = chatbots.find(item => Number(item.id) === this.pendingDeployChatbotId);
    if (!bot) return;
    const id = this.pendingDeployChatbotId;
    this.pendingDeployChatbotId = undefined;
    this.openPanel(bot, 'deploy');
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { chatbot_id: id, mode: 'deploy' },
      replaceUrl: true
    });
  }

  openWizard() {
    this.error.set('');
    this.success.set('');
    this.wizardOpen.set(true);
  }

  closeWizard() {
    if (this.creating()) return;
    this.wizardOpen.set(false);
  }

  finishWizard(state: any) {
    this.creating.set(true);
    this.error.set('');
    this.success.set('');

    this.api.createChatbot({
      assistant_type: state.assistant_type,
      creation_mode: state.creation_mode,
      name: state.name.trim(),
      description: state.description?.trim() || '',
      language: state.language,
      project_id: this.projectId,
      type: 'builder',
      purpose: state.assistant_type,
      mode: 'builder',
      channel: 'web_widget',
      build_method: state.creation_mode,
      template_key: null,
      status: 'draft',
      published: false
    }).subscribe({
      next: (created: any) => {
        this.creating.set(false);
        this.wizardOpen.set(false);
        this.success.set(`Assistant created as draft. Chatbot ID: ${created.id}`);
        this.navigateAfterCreation(state.creation_mode, created.id);
      },
      error: err => {
        this.creating.set(false);
        this.error.set(err.error?.detail || 'Could not create assistant');
      }
    });
  }

  navigateAfterCreation(creationMode: string, chatbotId: number) {
    const base = ['/dashboard/projects', this.projectId, 'chatbots', chatbotId];
    if (creationMode === 'template') {
      this.router.navigate([...base, 'templates']);
      return;
    }
    if (creationMode === 'ai') {
      this.router.navigate([...base, 'ai-generator']);
      return;
    }
    this.router.navigate([...base, 'flow']);
  }

  deleteChatbot(bot: any) {
    if (!confirm(`Delete chatbot "${bot.name}" and its versions?`)) return;

    this.deletingId.set(bot.id);
    this.api.deleteChatbot(bot.id).subscribe({
      next: () => {
        this.deletingId.set(undefined);
        if (this.selectedDetails()?.id === bot.id) {
          this.closeDetails();
        }
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not delete chatbot');
        this.deletingId.set(undefined);
      }
    });
  }

  openPanel(bot: any, mode: 'overview' | 'deploy' | 'settings') {
    this.detailsMode.set(mode);
    this.detailsLoading.set(true);
    this.error.set('');
    this.selectedDetails.set(null);

    this.api.getChatbot(bot.id).subscribe({
      next: details => {
        this.selectedDetails.set(details);
        this.detailsLoading.set(false);
        if (mode === 'deploy') {
          this.loadChannels(details.id);
        }
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load chatbot details');
        this.detailsLoading.set(false);
      }
    });
  }

  loadChannels(chatbotId: number) {
    this.channelsLoading.set(true);
    this.api.getChatbotChannels(chatbotId).subscribe({
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

  closeDetails() {
    this.selectedDetails.set(null);
    this.editingId.set(undefined);
  }

  startEdit(bot: any) {
    this.editingId.set(bot.id);
    this.error.set('');
    this.success.set('');
    this.editForm = {
      name: bot.name || '',
      description: bot.description || '',
      language: bot.language || 'fr',
      type: 'builder',
      purpose: bot.purpose || 'custom',
      mode: 'builder',
      channel: bot.channel || 'web_widget',
      template_key: bot.template_key || null
    };
  }

  cancelEdit() {
    this.editingId.set(undefined);
  }

  saveChatbot(bot: any) {
    const name = this.editForm.name.trim();
    if (!name) {
      this.error.set('Chatbot name is required');
      return;
    }

    this.savingId.set(bot.id);
    this.error.set('');
    this.success.set('');

    this.api.updateChatbot(bot.id, {
      ...this.editForm,
      type: 'builder',
      mode: 'builder',
      name,
      description: this.editForm.description.trim()
    }).subscribe({
      next: updated => {
        this.savingId.set(undefined);
        this.editingId.set(undefined);
        this.selectedDetails.update(details => details?.id === bot.id ? { ...details, ...updated } : details);
        this.success.set('Chatbot updated');
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update chatbot');
        this.savingId.set(undefined);
      }
    });
  }

  setActive(bot: any, isActive: boolean) {
    this.statusId.set(bot.id);
    this.error.set('');
    this.success.set('');

    this.api.updateChatbotStatus(bot.id, isActive).subscribe({
      next: updated => {
        this.statusId.set(undefined);
        this.selectedDetails.update(details => details?.id === bot.id ? { ...details, ...updated } : details);
        this.success.set(isActive ? 'Chatbot activated' : 'Chatbot deactivated');
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update chatbot status');
        this.statusId.set(undefined);
      }
    });
  }

  publicLink(bot: any) {
    return `${frontendBaseUrl()}/public-chat/${bot.id}`;
  }

  widgetCode(bot: any) {
    const baseUrl = apiBaseUrl();
    return `<script src="${baseUrl}/public/widget.js" data-api-base="${baseUrl}" data-chatbot-id="${bot.id}" data-title="${bot.name || 'Support'}"></script>`;
  }

  apiEndpoint() {
    return `${apiBaseUrl()}/public/api/chat`;
  }

  channel(type: string) {
    return this.channels().find(item => item.channel_type === type);
  }

  channelStatus(type: string) {
    return this.channel(type)?.status || (['web', 'widget', 'api'].includes(type) ? 'connected' : 'not_configured');
  }

  statusText(type: string) {
    const value = this.channelStatus(type);
    return value ? value.replace(/_/g, ' ') : 'disconnected';
  }

  masked(value: string | undefined) {
    return value ? '********' : 'Not configured';
  }

  saveChannel(bot: any, type: 'web' | 'widget' | 'api', config: any = {}) {
    this.channelSaving.set(type);
    this.error.set('');
    this.success.set('');
    this.api.updateChatbotChannel(bot.id, type, {
      status: 'configured',
      config_json: config
    }).subscribe({
      next: savedChannel => {
        this.channels.update(channels => {
          const existingIndex = channels.findIndex(item => item.channel_type === savedChannel.channel_type);
          if (existingIndex === -1) {
            return [...channels, savedChannel];
          }
          return channels.map(item => item.channel_type === savedChannel.channel_type ? savedChannel : item);
        });
        this.success.set(`${this.channelDisplayName(type)} channel saved`);
        this.channelSaving.set(undefined);
        this.loadChannels(bot.id);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save channel');
        this.channelSaving.set(undefined);
      }
    });
  }

  testChannel(bot: any, type: 'web' | 'widget' | 'api') {
    this.channelTesting.set(type);
    this.error.set('');
    this.success.set('');
    this.api.testChatbotChannel(bot.id, type).subscribe({
      next: result => {
        this.channelTesting.set(undefined);
        this.success.set(result.configured
          ? `${type} channel is configured.`
          : `${type} missing: ${(result.missing_fields || []).join(', ') || 'configuration'}`);
        this.loadChannels(bot.id);
      },
      error: err => {
        this.channelTesting.set(undefined);
        this.error.set(err.error?.detail || 'Could not test channel');
      }
    });
  }

  channelLog(type: string, key: 'last_verification' | 'last_incoming_message' | 'last_error') {
    return this.channel(type)?.[key];
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

  channelCurrentErrorAt(type: string) {
    const channel = this.channel(type);
    return channel?.last_error_log?.created_at || channel?.last_historical_error?.created_at || channel?.updated_at || '';
  }

  channelConfig(type: string) {
    return this.channel(type)?.config_json || {};
  }

  historicalChannelError(type: string) {
    const channel = this.channel(type);
    if (channel?.last_error) return '';
    return channel?.last_historical_error?.message || '';
  }

  historicalChannelErrorAt(type: string) {
    return this.channel(type)?.last_historical_error?.created_at || '';
  }

  clearChannelError(details: any, type: 'web' | 'widget' | 'api') {
    this.error.set('');
    this.success.set('');
    this.api.clearChatbotChannelError(details.id, type).subscribe({
      next: savedChannel => {
        this.channels.update(channels => channels.map(item => item.channel_type === savedChannel.channel_type ? savedChannel : item));
        this.success.set(`${this.channelDisplayName(type)} channel error cleared`);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not clear channel error');
      }
    });
  }

  channelStatusLabel(type: string) {
    const value = this.channelStatus(type);
    const labels: Record<string, string> = {
      disconnected: 'Not Configured',
      not_configured: 'Not Configured',
      configured: 'Configured',
      verified: 'Verified',
      connected: 'Connected',
      deployed: 'Connected',
      error: 'Error'
    };
    return labels[value] || value || 'Not Configured';
  }

  channelStatusClass(type: string) {
    return `channel-status-${this.channelStatus(type)}`;
  }

  widgetCustomizationPlaceholder() {
    this.success.set('Widget customization will open the customization workspace in a later step.');
  }

  apiCurl(bot: any) {
    return `curl -X POST "${this.apiEndpoint()}" -H "Content-Type: application/json" -H "x-chatbot-api-key: ${bot.public_api_key}" -d "{\\"chatbot_id\\":${bot.id},\\"message\\":\\"Hello\\",\\"session_id\\":null}"`;
  }

  maskedApiKey(bot: any) {
    const key = bot.public_api_key || '';
    if (!key) return 'Not generated';
    return `${key.slice(0, 5)}${'*'.repeat(18)}${key.slice(-4)}`;
  }

  copyText(text: string) {
    if (!text) {
      this.error.set('No value available to copy');
      return;
    }
    if (!this.isBrowser || !navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(() => {
      this.success.set('Copied');
    });
  }

  regenerateApiKey(bot: any) {
    if (!confirm('Regenerate API key? Existing external apps using the old key will stop working.')) return;

    this.apiKeyId.set(bot.id);
    this.error.set('');
    this.success.set('');

    this.api.regenerateChatbotApiKey(bot.id).subscribe({
      next: response => {
        this.apiKeyId.set(undefined);
        this.success.set('API key regenerated');
        this.selectedDetails.update(details => details ? { ...details, public_api_key: response.public_api_key } : details);
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not regenerate API key');
        this.apiKeyId.set(undefined);
      }
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId]);
  }
}
