import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-versions',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './versions.component.html',
  styleUrls: ['./versions.component.css']
})
export class VersionsComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;
  versions = signal<any[]>([]);
  selectedVersionId = signal<number | undefined>(undefined);
  documents = signal<any[]>([]);
  selectedFileName = '';
  uploadError = signal('');
  uploadLoading = signal(false);
  chatQuestion = '';
  chatAnswer = signal('');
  chatMessages = signal<{ text: string; options?: string[] }[]>([]);
  chatSources = signal<any[]>([]);
  chatOptions = signal<string[]>([]);
  chatSessionId = signal<number | undefined>(undefined);
  chatLoading = signal(false);
  chatError = signal('');
  configLoading = signal(false);
  configSaving = signal(false);
  configMessage = signal('');
  loading = signal(false);
  creating = signal(false);
  actionId = signal<number | undefined>(undefined);
  error = signal('');
  private isBrowser: boolean;
  aiInstructions = {
    model: 'llama3',
    temperature: 0.7,
    system_instructions: '',
    tone: 'Professional',
    language: 'French',
    response_style: 'Concise'
  };

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
    this.loadVersions();
  }

  loadVersions() {
    if (!this.isBrowser) return;

    this.loading.set(true);
    this.error.set('');

    this.api.getVersionsByChatbot(this.chatbotId).subscribe({
      next: versions => {
        const sortedVersions = versions.sort((a: any, b: any) => b.version_number - a.version_number);
        const activeVersion = sortedVersions.find((version: any) => version.is_active);
        const publishedVersion = sortedVersions.find((version: any) => version.status === 'published');
        const selectedVersionId = activeVersion?.id || publishedVersion?.id || sortedVersions[0]?.id;
        this.versions.set(sortedVersions);
        this.selectedVersionId.set(selectedVersionId);
        this.loading.set(false);

        if (selectedVersionId) {
          this.loadDocuments(selectedVersionId);
          this.loadLlmConfig(selectedVersionId);
        } else {
          this.documents.set([]);
        }
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load versions');
        this.loading.set(false);
      }
    });
  }

  createVersion() {
    this.creating.set(true);
    this.error.set('');

    this.api.createVersion({ chatbot_id: this.chatbotId }).subscribe({
      next: () => {
        this.creating.set(false);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not create version');
        this.creating.set(false);
      }
    });
  }

  publish(versionId: number) {
    this.actionId.set(versionId);
    this.error.set('');

    this.api.validateFlow(versionId).subscribe({
      next: validation => {
        const errors = validation?.errors || [];
        if (errors.length) {
          this.error.set(`Fix these flow issues before publishing: ${errors.join(' ')}`);
          this.actionId.set(undefined);
          return;
        }

        this.api.publishVersion(versionId).subscribe({
          next: () => {
            this.actionId.set(undefined);
            this.loadVersions();
          },
          error: err => {
            this.error.set(this.publishError(err));
            this.actionId.set(undefined);
          }
        });
      },
      error: err => {
        this.error.set(this.publishError(err));
        this.actionId.set(undefined);
      }
    });
  }

  archive(versionId: number) {
    this.actionId.set(versionId);
    this.api.archiveVersion(versionId).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not archive version');
        this.actionId.set(undefined);
      }
    });
  }

  duplicate(versionId: number) {
    this.actionId.set(versionId);
    this.error.set('');
    this.api.duplicateVersion(versionId).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not duplicate version');
        this.actionId.set(undefined);
      }
    });
  }

  deleteVersion(version: any) {
    if (!confirm(`Delete version ${version.version_number}?`)) return;

    this.actionId.set(version.id);
    this.api.deleteVersion(version.id).subscribe({
      next: () => {
        this.actionId.set(undefined);
        this.loadVersions();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not delete version');
        this.actionId.set(undefined);
      }
    });
  }

  selectVersion(versionId: number) {
    this.selectedVersionId.set(versionId);
    this.chatAnswer.set('');
    this.chatSources.set([]);
    this.chatMessages.set([]);
    this.chatOptions.set([]);
    this.chatSessionId.set(undefined);
    this.loadDocuments(versionId);
    this.loadLlmConfig(versionId);
  }

  loadLlmConfig(versionId: number) {
    this.configLoading.set(true);
    this.configMessage.set('');
    this.api.getLlmConfig(versionId).subscribe({
      next: config => {
        this.aiInstructions = this.parseSystemPrompt(config);
        this.configLoading.set(false);
      },
      error: () => {
        this.aiInstructions = {
          model: 'llama3',
          temperature: 0.7,
          system_instructions: '',
          tone: 'Professional',
          language: 'French',
          response_style: 'Concise'
        };
        this.configLoading.set(false);
      }
    });
  }

  saveLlmConfig() {
    const versionId = this.selectedVersionId();
    if (!versionId) return;

    this.configSaving.set(true);
    this.configMessage.set('');
    this.api.saveLlmConfig({
      version_id: versionId,
      model: this.aiInstructions.model || 'llama3',
      temperature: Number(this.aiInstructions.temperature) || 0.7,
      system_prompt: this.buildSystemPrompt()
    }).subscribe({
      next: () => {
        this.configSaving.set(false);
        this.configMessage.set('AI instructions saved');
      },
      error: err => {
        this.configSaving.set(false);
        this.configMessage.set(err.error?.detail || 'Could not save AI instructions');
      }
    });
  }

  private parseSystemPrompt(config: any) {
    const prompt = config.system_prompt || '';
    return {
      model: config.model || 'llama3',
      temperature: config.temperature ?? 0.7,
      system_instructions: prompt,
      tone: this.extractPromptValue(prompt, 'Tone') || 'Professional',
      language: this.extractPromptValue(prompt, 'Language') || 'French',
      response_style: this.extractPromptValue(prompt, 'Response style') || 'Concise'
    };
  }

  private extractPromptValue(prompt: string, label: string) {
    const line = prompt.split('\n').find(item => item.toLowerCase().startsWith(`${label.toLowerCase()}:`));
    return line ? line.split(':').slice(1).join(':').trim() : '';
  }

  private buildSystemPrompt() {
    const base = this.aiInstructions.system_instructions.trim() || 'You are a helpful assistant.';
    return [
      base,
      `Tone: ${this.aiInstructions.tone}`,
      `Language: ${this.aiInstructions.language}`,
      `Response style: ${this.aiInstructions.response_style}`
    ].join('\n');
  }

  loadDocuments(versionId: number) {
    this.uploadError.set('');

    this.api.getDocuments(versionId).subscribe({
      next: documents => {
        this.documents.set(documents);
      },
      error: err => {
        this.uploadError.set(err.error?.detail || 'Could not load documents');
      }
    });
  }

  deleteDocument(document: any) {
    if (!confirm(`Delete document "${document.filename}"?`)) return;

    this.api.deleteDocument(document.id).subscribe({
      next: () => {
        const selectedVersionId = this.selectedVersionId();
        if (selectedVersionId) this.loadDocuments(selectedVersionId);
      },
      error: err => {
        this.uploadError.set(err.error?.detail || 'Could not delete document');
      }
    });
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];

    this.uploadError.set('');
    this.selectedFileName = file?.name || '';

    const selectedVersionId = this.selectedVersionId();
    if (!file || !selectedVersionId) return;

    this.uploadLoading.set(true);
    const reader = new FileReader();

    reader.onload = () => {
      this.api.uploadDocument(selectedVersionId, {
        filename: file.name,
        content_type: file.type || 'text/plain',
        content: String(reader.result || '')
      }).subscribe({
        next: () => {
          this.loadDocuments(selectedVersionId);
          input.value = '';
          this.selectedFileName = '';
          this.uploadLoading.set(false);
        },
        error: err => {
          this.uploadError.set(err.error?.detail || 'Upload failed');
          this.uploadLoading.set(false);
        }
      });
    };

    reader.onerror = () => {
      this.uploadError.set('Could not read file');
      this.uploadLoading.set(false);
    };

    reader.readAsText(file);
  }

  askChatbot() {
    if (!this.chatQuestion.trim()) return;

    this.chatLoading.set(true);
    this.chatError.set('');
    this.chatAnswer.set('');
    this.chatMessages.set([]);
    this.chatSources.set([]);
    this.chatOptions.set([]);

    this.api.chat({
      chatbot_id: this.chatbotId,
      message: this.chatQuestion,
      session_id: this.chatSessionId(),
      version_id: this.selectedVersionId()
    }).subscribe({
      next: res => {
        this.chatAnswer.set(res.response);
        this.chatMessages.set(this.toChatMessages(res));
        this.chatSources.set(res.sources || []);
        this.chatOptions.set(res.options || []);
        this.chatSessionId.set(res.session_id);
        this.chatLoading.set(false);
      },
      error: err => {
        this.chatError.set(err.error?.detail || 'Chat failed');
        this.chatLoading.set(false);
      }
    });
  }

  askOption(option: string) {
    this.chatQuestion = option;
    this.askChatbot();
  }

  private toChatMessages(response: any) {
    if (Array.isArray(response.messages) && response.messages.length > 0) {
      return response.messages.map((item: any) => ({
        text: item.text || '',
        options: item.options || []
      }));
    }

    return [{
      text: response.response || '',
      options: response.options || []
    }];
  }

  private publishError(err: any) {
    const detail = err?.error?.detail;
    if (Array.isArray(detail?.errors)) {
      return `Fix these flow issues before publishing: ${detail.errors.join(' ')}`;
    }
    if (typeof detail?.message === 'string') return detail.message;
    if (typeof detail === 'string') return detail;
    return 'Could not publish version';
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }
}
