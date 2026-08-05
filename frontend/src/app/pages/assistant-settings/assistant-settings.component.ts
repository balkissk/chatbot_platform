import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import {
  LucideBot,
  LucideCheckCircle2,
  LucideSave,
  LucideSlidersHorizontal
} from '@lucide/angular';
import { ApiService } from '../../services/api';
import { ToastService } from '../../services/toast.service';
import {
  ASSISTANT_CHANNEL_OPTIONS,
  ASSISTANT_LANGUAGE_OPTIONS,
  channelLabel,
  languageLabel,
  normalizeAssistantChannel,
  normalizeAssistantLanguage,
  purposeLabel
} from '../../shared/assistant-options';

@Component({
  selector: 'app-assistant-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    LucideBot,
    LucideCheckCircle2,
    LucideSave,
    LucideSlidersHorizontal
  ],
  templateUrl: './assistant-settings.component.html',
  styleUrls: ['./assistant-settings.component.css']
})
export class AssistantSettingsComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;
  assistant = signal<any | null>(null);
  project = signal<any | null>(null);
  loading = signal(false);
  saving = signal(false);
  statusSaving = signal(false);
  deleting = signal(false);
  confirmDeleteOpen = signal(false);
  error = signal('');
  message = signal('');
  languageOptions = ASSISTANT_LANGUAGE_OPTIONS;
  channelOptions = ASSISTANT_CHANNEL_OPTIONS;
  form = {
    name: '',
    description: '',
    language: 'fr',
    channel: 'web_widget',
    type: 'builder',
    purpose: 'custom',
    mode: 'builder',
    template_key: null as string | null
  };
  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
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
        this.populateForm(assistant);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load assistant settings');
        this.loading.set(false);
      }
    });
  }

  populateForm(assistant: any) {
    this.form = {
      name: assistant.name || '',
      description: assistant.description || '',
      language: normalizeAssistantLanguage(assistant.language),
      channel: normalizeAssistantChannel(assistant.channel),
      type: 'builder',
      purpose: assistant.purpose || 'custom',
      mode: 'builder',
      template_key: assistant.template_key || null
    };
  }

  saveSettings() {
    const name = this.form.name.trim();
    if (!name) {
      this.error.set('Assistant name is required');
      return;
    }
    this.saving.set(true);
    this.error.set('');
    this.message.set('');
    this.api.updateChatbot(this.chatbotId, {
      ...this.form,
      type: 'builder',
      mode: 'builder',
      name,
      description: this.form.description.trim(),
      language: normalizeAssistantLanguage(this.form.language),
      channel: normalizeAssistantChannel(this.form.channel)
    }).subscribe({
      next: assistant => {
        this.assistant.set({ ...this.assistant(), ...assistant });
        this.populateForm({ ...this.assistant(), ...assistant });
        this.saving.set(false);
        this.message.set('Assistant settings saved');
        this.toast.success('Assistant settings saved');
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save assistant settings');
        this.saving.set(false);
      }
    });
  }

  setActive(isActive: boolean) {
    this.statusSaving.set(true);
    this.error.set('');
    this.message.set('');
    this.api.updateChatbotStatus(this.chatbotId, isActive).subscribe({
      next: assistant => {
        this.assistant.set({ ...this.assistant(), ...assistant });
        this.statusSaving.set(false);
        this.message.set(isActive ? 'Assistant activated' : 'Assistant deactivated');
        this.toast.success(isActive ? 'Assistant activated' : 'Assistant deactivated');
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update assistant status');
        this.statusSaving.set(false);
      }
    });
  }

  deleteAssistant() {
    this.deleting.set(true);
    this.error.set('');
    this.api.deleteChatbot(this.chatbotId).subscribe({
      next: () => {
        this.toast.success('Assistant deleted');
        this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not delete assistant');
        this.deleting.set(false);
      }
    });
  }

  isArchivedProject() {
    return String(this.project()?.status || '').toLowerCase() === 'archived';
  }

  statusLabel() {
    return this.assistant()?.is_active ? 'Live' : 'Draft';
  }

  purposeLabel() {
    const assistant = this.assistant();
    return purposeLabel(assistant?.purpose || assistant?.assistant_type);
  }

  languageLabel() {
    return languageLabel(this.assistant()?.language);
  }

  channelLabel() {
    return channelLabel(this.assistant()?.channel);
  }
}
