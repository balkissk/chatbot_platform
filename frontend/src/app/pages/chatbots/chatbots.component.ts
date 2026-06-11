import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';
import { apiBaseUrl, frontendBaseUrl } from '../../config/app-config';

@Component({
  selector: 'app-chatbots',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './chatbots.component.html',
  styleUrls: ['./chatbots.component.css']
})
export class ChatbotsComponent implements OnInit {
  projectId!: number;
  project = signal<any | null>(null);
  chatbots = signal<any[]>([]);
  newChatbotName = '';
  description = '';
  language = 'fr';
  loading = signal(false);
  refreshing = signal(false);
  creating = signal(false);
  savingId = signal<number | undefined>(undefined);
  deletingId = signal<number | undefined>(undefined);
  statusId = signal<number | undefined>(undefined);
  apiKeyId = signal<number | undefined>(undefined);
  editingId = signal<number | undefined>(undefined);
  selectedDetails = signal<any | null>(null);
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
  private isBrowser: boolean;

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
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load chatbots');
        this.loading.set(false);
        this.refreshing.set(false);
      }
    });
  }

  createChatbot() {
    const name = this.newChatbotName.trim();
    if (!name) return;

    this.creating.set(true);
    this.error.set('');

    this.api.createChatbot({
      name,
      description: this.description.trim(),
      project_id: this.projectId,
      language: this.language,
      type: 'builder',
      purpose: 'custom',
      mode: 'builder',
      channel: 'web_widget',
      build_method: 'blank',
      template_key: null
    }).subscribe({
      next: (created: any) => {
        this.newChatbotName = '';
        this.description = '';
        this.creating.set(false);
        this.success.set('Chatbot created with an initial draft version');
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not create chatbot');
        this.creating.set(false);
      }
    });
  }

  deleteChatbot(bot: any) {
    if (!confirm(`Delete chatbot "${bot.name}" and its versions?`)) return;

    this.deletingId.set(bot.id);
    this.api.deleteChatbot(bot.id).subscribe({
      next: () => {
        this.deletingId.set(undefined);
        this.loadChatbots(true, true);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not delete chatbot');
        this.deletingId.set(undefined);
      }
    });
  }

  viewDetails(bot: any) {
    this.detailsLoading.set(true);
    this.error.set('');
    this.selectedDetails.set(null);

    this.api.getChatbot(bot.id).subscribe({
      next: details => {
        this.selectedDetails.set(details);
        this.detailsLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load chatbot details');
        this.detailsLoading.set(false);
      }
    });
  }

  closeDetails() {
    this.selectedDetails.set(null);
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
      next: () => {
        this.savingId.set(undefined);
        this.editingId.set(undefined);
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
      next: () => {
        this.statusId.set(undefined);
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

  apiCurl(bot: any) {
    return `curl -X POST "${this.apiEndpoint()}" -H "Content-Type: application/json" -H "x-chatbot-api-key: ${bot.public_api_key}" -d "{\\"chatbot_id\\":${bot.id},\\"message\\":\\"Hello\\",\\"session_id\\":null}"`;
  }

  copyText(text: string) {
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
